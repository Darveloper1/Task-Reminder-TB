from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
import json
from datetime import datetime, time, timedelta
import os
import pytz
from telegram.ext import JobQueue


# States for conversation handlers
TASK_NAME, TASK_CATEGORY, TASK_DUE_DATE = range(3)
DELETE_CONFIRMATION = 0
FREQUENCY_SELECTION = 0

class TaskBot:
    def __init__(self, token):
        # Initialize data storage - now includes reminder frequency
        self.user_data = {}  # Format: {user_id: {'tasks': [], 'categories': set(), 'reminder_frequency': '24h'}}
        self.load_data()
        
        # Create application with job queue
        self.app = (
            ApplicationBuilder()
            .token(token)
            .job_queue(JobQueue())
            .build()
        )
        
        self.setup_handlers()
        self.setup_reminder_job()

        self.frequency_options = {
            '24h': {'hours': 24, 'label': 'Every 24 hours'},
            '48h': {'hours': 48, 'label': 'Every 48 hours'},
            '1w': {'hours': 168, 'label': 'Every week'}
        }

    def load_data(self):
        """Load all users' tasks and categories from file if it exists"""
        if os.path.exists('user_tasks.json'):
            with open('user_tasks.json', 'r') as f:
                data = json.load(f)
                # Convert string user_ids back to integers and categories back to sets
                self.user_data = {
                    int(user_id): {
                        'tasks': user_data['tasks'],
                        'categories': set(user_data['categories']),
                        'reminder_frequency': user_data.get('reminder_frequency', '24h'),
                        'last_reminder': user_data.get('last_reminder', '01-01-2000')
                    }
                    for user_id, user_data in data.items()
                }

    def save_data(self):
        """Save all users' tasks and categories to file"""
        # Convert sets to lists for JSON serialization
        serializable_data = {
            str(user_id): {
                'tasks': user_data['tasks'],
                'categories': list(user_data['categories']),
                'reminder_frequency': user_data.get('reminder_frequency', '24h'),
                'last_reminder': user_data.get('last_reminder', '01-01-2000')
            }
            for user_id, user_data in self.user_data.items()
        }
        with open('user_tasks.json', 'w') as f:
            json.dump(serializable_data, f)

    def setup_reminder_job(self):
        """Setup daily job to check and send reminders"""
        # Schedule job to run at 9AM SGT (UTC+8)
        target_time = time(hour=9, minute=0)
        
        # Add daily job
        self.app.job_queue.run_daily(
            self.send_reminders,
            time=target_time
        )

    async def send_reminders(self, context: ContextTypes.DEFAULT_TYPE):
        """Send reminders to users based on their frequency settings"""
        current_time = datetime.now(pytz.timezone('Asia/Singapore'))
        print(f"Running reminders check at {current_time}")  # Debug log
        
        for user_id, user_data in self.user_data.items():
            try:
                # First cleanup old tasks
                await self.cleanup_old_tasks(context, user_id, user_data)
                
                frequency = user_data.get('reminder_frequency', '24h')
                last_reminder = datetime.strptime(user_data.get('last_reminder', '01-01-2000'), '%d-%m-%Y')
                
                # Check if it's time to send reminder based on frequency
                hours_diff = (current_time - last_reminder.astimezone(pytz.timezone('Asia/Singapore'))).total_seconds() / 3600
                if hours_diff >= self.frequency_options[frequency]['hours']:
                    if user_data['tasks']:
                        print(f"Sending reminder to user {user_id}")  # Debug log
                        await self.send_task_list(context, user_id, is_reminder=True)
                        self.user_data[user_id]['last_reminder'] = current_time.isoformat()
                        self.save_data()
            except Exception as e:
                print(f"Error sending reminder to user {user_id}: {str(e)}")  # Debug log

    def get_user_data(self, user_id: int):
        """Get or initialize user data"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'tasks': [],
                'categories': set(),
                'reminder_frequency': '24h',
                'last_reminder': datetime.now(pytz.timezone('Asia/Singapore')).strftime('%d-%m-%Y')
            }
        return self.user_data[user_id]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Updated start command with new command list"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)
        
        await update.message.reply_text(
            f"Welcome to your Personal Task Manager!\n\n"
            f"Available commands:\n"
            f"/new - Create a new task\n"
            f"/tasklist - List all your tasks\n"
            f"/delete - Delete a task\n"
            f"/frequency - Set reminder frequency\n"
            f"/categories - Manage your categories"
        )

    async def new_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the new task conversation"""
        user_id = update.effective_user.id
        context.user_data['user_id'] = user_id  # Store user_id for later use
        await update.message.reply_text("What's the name of your task?")
        return TASK_NAME

    async def receive_task_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle task name input and ask for category"""
        user_id = context.user_data['user_id']
        user_data = self.get_user_data(user_id)
        
        # If we're expecting a new category name (set by receive_category)
        if context.user_data.get('waiting_for_new_category'):
            context.user_data['category'] = update.message.text
            context.user_data['waiting_for_new_category'] = False
            await update.message.reply_text(
                "When is this task due? (Format: DD-MM-YYYY)"
            )
            return TASK_DUE_DATE
        
        # Regular flow for task name
        context.user_data['task_name'] = update.message.text
        
        # Create keyboard with user's existing categories
        keyboard = [[InlineKeyboardButton(cat, callback_data=cat)] for cat in user_data['categories']]
        keyboard.append([InlineKeyboardButton("New Category", callback_data="new_category")])
        
        await update.message.reply_text(
            "Select a category or create a new one:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return TASK_CATEGORY

    async def receive_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle category selection and ask for due date"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "new_category":
            context.user_data['waiting_for_new_category'] = True
            await query.message.reply_text("Enter the name of the new category:")
            return TASK_NAME  # Return to receive_task_name to handle the new category input
        
        context.user_data['category'] = query.data
        await query.message.reply_text(
            "When is this task due? (Format: DD-MM-YYYY)"
        )
        return TASK_DUE_DATE

    async def receive_due_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Finalize task creation"""
        user_id = context.user_data['user_id']
        user_data = self.get_user_data(user_id)
        
        try:
            due_date = datetime.strptime(update.message.text, '%d-%m-%Y').strftime('%d-%m-%Y')
            task = {
                'name': context.user_data['task_name'],
                'category': context.user_data['category'],
                'due_date': due_date
            }
            user_data['tasks'].append(task)
            user_data['categories'].add(task['category'])
            self.save_data()
            
            await update.message.reply_text(
                f"Task created successfully!\n"
                f"Name: {task['name']}\n"
                f"Category: {task['category']}\n"
                f"Due Date: {task['due_date']}"
            )
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text(
                "Invalid date format. Please use DD-MM-YYYY.\n"
                "Task creation cancelled."
            )
            return ConversationHandler.END

    async def set_frequency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the frequency command"""
        keyboard = [
            [InlineKeyboardButton(details['label'], callback_data=f"freq_{freq}")]
            for freq, details in self.frequency_options.items()
        ]
        
        await update.message.reply_text(
            "Select how often you want to receive reminders:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return FREQUENCY_SELECTION

    async def handle_frequency_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle frequency selection callback"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        frequency = query.data.split('_')[1]
        
        user_data = self.get_user_data(user_id)
        user_data['reminder_frequency'] = frequency
        self.save_data()
        
        await query.message.reply_text(
            f"Reminder frequency set to: {self.frequency_options[frequency]['label']}\n"
            f"You'll receive reminders at 9:00 AM (UTC+8)"
        )
        return ConversationHandler.END

    async def send_task_list(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, is_reminder: bool = False):
        """Send task list to user"""
        user_data = self.get_user_data(user_id)
        
        if not user_data['tasks']:
            if not is_reminder:
                await context.bot.send_message(user_id, "You have no tasks!")
            return

        # Group tasks by category
        tasks_by_category = {}
        for task in user_data['tasks']:
            category = task['category']
            if category not in tasks_by_category:
                tasks_by_category[category] = []
            tasks_by_category[category].append(task)

        # Create formatted message
        prefix = "🔔 Reminder of your tasks:" if is_reminder else "Your Tasks:"
        message = f"{prefix}\n\n"
        
        for category, tasks in tasks_by_category.items():
            message += f"📁 {category}:\n"
            for task in tasks:
                message += f"   • {task['name']} (Due: {task['due_date']})\n"
            message += "\n"

        await context.bot.send_message(user_id, message)

    async def tasklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the tasklist command"""
        user_id = update.effective_user.id
        await self.send_task_list(context, user_id)

    async def delete_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show tasks that can be deleted for the specific user"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)
        
        if not user_data['tasks']:
            await update.message.reply_text("You have no tasks to delete!")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(f"{task['name']} ({task['category']})", 
                                callback_data=f"delete_{i}")] 
            for i, task in enumerate(user_data['tasks'])
        ]
        
        context.user_data['user_id'] = user_id  # Store for deletion confirmation
        
        await update.message.reply_text(
            "Select a task to delete:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return DELETE_CONFIRMATION

    async def confirm_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle task deletion for the specific user"""
        query = update.callback_query
        await query.answer()
        
        user_id = context.user_data['user_id']
        user_data = self.get_user_data(user_id)
        
        task_index = int(query.data.split('_')[1])
        deleted_task = user_data['tasks'].pop(task_index)
        
        # Remove category if no tasks use it
        category = deleted_task['category']
        if not any(task['category'] == category for task in user_data['tasks']):
            user_data['categories'].remove(category)
        
        self.save_data()
        
        await query.message.reply_text(
            f"Deleted task: {deleted_task['name']}"
        )
        return ConversationHandler.END
    
    async def cleanup_old_tasks(self, context: ContextTypes.DEFAULT_TYPE, user_id: int, user_data: dict):
        """Remove tasks that are more than a day past their due date"""
        current_date = datetime.now(pytz.timezone('Asia/Singapore')).date()
        tasks_to_remove = []
        
        for index, task in enumerate(user_data['tasks']):
            task_due_date = datetime.strptime(task['due_date'], '%d-%m-%Y').date()
            days_overdue = (current_date - task_due_date).days
            
            if days_overdue > 0:
                tasks_to_remove.append(index)
        
        # Remove tasks in reverse order to maintain correct indices
        for index in reversed(tasks_to_remove):
            removed_task = user_data['tasks'].pop(index)
            
            # Check if we need to remove the category
            category = removed_task['category']
            if not any(task['category'] == category for task in user_data['tasks']):
                user_data['categories'].remove(category)
                
        if tasks_to_remove:
            self.save_data()
            if len(tasks_to_remove) == 1:
                await context.bot.send_message(
                    user_id, 
                    "1 expired task has been automatically removed."
                )
            else:
                await context.bot.send_message(
                    user_id, 
                    f"{len(tasks_to_remove)} expired tasks have been automatically removed."
                )
    
    async def list_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all categories for the user"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)
        
        if not user_data['categories']:
            await update.message.reply_text("You don't have any categories yet!")
            return
        
        # Create message showing categories and number of tasks in each
        message = "Your Categories:\n\n"
        for category in sorted(user_data['categories']):
            task_count = len([task for task in user_data['tasks'] if task['category'] == category])
            message += f"📁 {category} ({task_count} tasks)\n"
        
        await update.message.reply_text(message)
    
    async def cancel_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the task creation process"""
        await update.message.reply_text(
            "Task creation cancelled. You can start a new task with /new"
        )
        return ConversationHandler.END

    def setup_handlers(self):
        """Set up all conversation handlers"""
        # Create task conversation handler with modified states
        create_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('new', self.new_task)],
            states={
                TASK_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_task_name)
                ],
                TASK_CATEGORY: [
                    CallbackQueryHandler(self.receive_category),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_task_name)
                ],
                TASK_DUE_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_due_date)
                ]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_task),
                MessageHandler(filters.COMMAND, self.cancel_task)
            ],
            name="create_task",
            persistent=False,
            allow_reentry=True
        )

        # Rest of your handlers remain the same...
        delete_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('delete', self.delete_task)],
            states={
                DELETE_CONFIRMATION: [CallbackQueryHandler(self.confirm_delete)]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_task)]
        )

        freq_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('frequency', self.set_frequency)],
            states={
                FREQUENCY_SELECTION: [CallbackQueryHandler(self.handle_frequency_selection)]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_task)]
        )

        # Make sure these handlers are added in this specific order
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(create_conv_handler)  # Put create_conv_handler early
        self.app.add_handler(CommandHandler('tasklist', self.tasklist))
        self.app.add_handler(delete_conv_handler)
        self.app.add_handler(freq_conv_handler)
        self.app.add_handler(CommandHandler('categories', self.list_categories))

    def run(self):
        """Start the bot"""
        self.app.run_polling()

if __name__ == '__main__':
    TOKEN = "YOUR_TOKEN_KEY"
    bot = TaskBot(TOKEN)
    bot.run()