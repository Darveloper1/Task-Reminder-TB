from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
import json
from datetime import datetime
import os

# States for conversation handler
TASK_NAME, TASK_CATEGORY, TASK_DUE_DATE = range(3)
DELETE_CONFIRMATION = 0

class TaskBot:
    def __init__(self, token):
        # Initialize data storage - now a dictionary with user_id as key
        self.user_data = {}  # Format: {user_id: {'tasks': [], 'categories': set()}}
        self.load_data()
        
        # Create application
        self.app = ApplicationBuilder().token(token).build()
        self.setup_handlers()

    def load_data(self):
        """Load all users' tasks and categories from file if it exists"""
        if os.path.exists('user_tasks.json'):
            with open('user_tasks.json', 'r') as f:
                data = json.load(f)
                # Convert string user_ids back to integers and categories back to sets
                self.user_data = {
                    int(user_id): {
                        'tasks': user_data['tasks'],
                        'categories': set(user_data['categories'])
                    }
                    for user_id, user_data in data.items()
                }

    def save_data(self):
        """Save all users' tasks and categories to file"""
        # Convert sets to lists for JSON serialization
        serializable_data = {
            str(user_id): {
                'tasks': user_data['tasks'],
                'categories': list(user_data['categories'])
            }
            for user_id, user_data in self.user_data.items()
        }
        with open('user_tasks.json', 'w') as f:
            json.dump(serializable_data, f)

    def get_user_data(self, user_id: int):
        """Get or initialize user data"""
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'tasks': [],
                'categories': set()
            }
        return self.user_data[user_id]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message with available commands"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)  # Initialize user data if needed
        
        await update.message.reply_text(
            f"Welcome to your Personal Task Manager!\n\n"
            f"Available commands:\n"
            f"/new - Create a new task\n"
            f"/list - List all your tasks\n"
            f"/delete - Delete a task\n"
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
            await query.message.reply_text("Enter the name of the new category:")
            return TASK_CATEGORY
        
        context.user_data['category'] = query.data
        await query.message.reply_text(
            "When is this task due? (Format: YYYY-MM-DD)"
        )
        return TASK_DUE_DATE

    async def receive_due_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Finalize task creation"""
        user_id = context.user_data['user_id']
        user_data = self.get_user_data(user_id)
        
        try:
            due_date = datetime.strptime(update.message.text, '%Y-%m-%d').strftime('%Y-%m-%d')
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
        except ValueError:
            await update.message.reply_text(
                "Invalid date format. Please use YYYY-MM-DD.\n"
                "Task creation cancelled."
            )
        
        return ConversationHandler.END

    async def list_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all tasks grouped by category for the specific user"""
        user_id = update.effective_user.id
        user_data = self.get_user_data(user_id)
        
        if not user_data['tasks']:
            await update.message.reply_text("You have no tasks!")
            return

        # Group tasks by category
        tasks_by_category = {}
        for task in user_data['tasks']:
            category = task['category']
            if category not in tasks_by_category:
                tasks_by_category[category] = []
            tasks_by_category[category].append(task)

        # Create formatted message
        message = "Your Tasks:\n\n"
        for category, tasks in tasks_by_category.items():
            message += f"📁 {category}:\n"
            for task in tasks:
                message += f"   • {task['name']} (Due: {task['due_date']})\n"
            message += "\n"

        await update.message.reply_text(message)

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

    def setup_handlers(self):
        """Set up all conversation handlers"""
        # Create task conversation handler
        create_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('new', self.new_task)],
            states={
                TASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_task_name)],
                TASK_CATEGORY: [
                    CallbackQueryHandler(self.receive_category),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_task_name)
                ],
                TASK_DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_due_date)]
            },
            fallbacks=[]
        )

        # Delete task conversation handler
        delete_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('delete', self.delete_task)],
            states={
                DELETE_CONFIRMATION: [CallbackQueryHandler(self.confirm_delete)]
            },
            fallbacks=[]
        )

        # Add handlers
        self.app.add_handler(CommandHandler('start', self.start))
        self.app.add_handler(CommandHandler('list', self.list_tasks))
        self.app.add_handler(create_conv_handler)
        self.app.add_handler(delete_conv_handler)

    def run(self):
        """Start the bot"""
        self.app.run_polling()

if __name__ == '__main__':
    TOKEN = "TELEGRAM_BOT_TOKEN"
    bot = TaskBot(TOKEN)
    bot.run()