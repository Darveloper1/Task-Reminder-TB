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
        # Initialize data storage
        self.tasks = []
        self.categories = set()
        self.load_data()
        
        # Create application
        self.app = ApplicationBuilder().token(token).build()
        self.setup_handlers()

    def load_data(self):
        """Load tasks and categories from file if it exists"""
        if os.path.exists('tasks.json'):
            with open('tasks.json', 'r') as f:
                data = json.load(f)
                self.tasks = data['tasks']
                self.categories = set(data['categories'])

    def save_data(self):
        """Save tasks and categories to file"""
        with open('tasks.json', 'w') as f:
            json.dump({
                'tasks': self.tasks,
                'categories': list(self.categories)
            }, f)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message with available commands"""
        await update.message.reply_text(
            "Welcome to your Task Manager Bot!\n\n"
            "Available commands:\n"
            "/new - Create a new task\n"
            "/list - List all tasks\n"
            "/delete - Delete a task\n"
            "/categories - Manage categories"
        )

    async def new_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the new task conversation"""
        await update.message.reply_text("What's the name of your task?")
        return TASK_NAME

    async def receive_task_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle task name input and ask for category"""
        context.user_data['task_name'] = update.message.text
        
        # Create keyboard with existing categories
        keyboard = [[InlineKeyboardButton(cat, callback_data=cat)] for cat in self.categories]
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
        try:
            due_date = datetime.strptime(update.message.text, '%Y-%m-%d').strftime('%Y-%m-%d')
            task = {
                'name': context.user_data['task_name'],
                'category': context.user_data['category'],
                'due_date': due_date
            }
            self.tasks.append(task)
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
        """List all tasks grouped by category"""
        if not self.tasks:
            await update.message.reply_text("No tasks found!")
            return

        # Group tasks by category
        tasks_by_category = {}
        for task in self.tasks:
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
        """Show tasks that can be deleted"""
        if not self.tasks:
            await update.message.reply_text("No tasks to delete!")
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(f"{task['name']} ({task['category']})", 
                                callback_data=f"delete_{i}")] 
            for i, task in enumerate(self.tasks)
        ]
        
        await update.message.reply_text(
            "Select a task to delete:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return DELETE_CONFIRMATION

    async def confirm_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle task deletion"""
        query = update.callback_query
        await query.answer()
        
        task_index = int(query.data.split('_')[1])
        deleted_task = self.tasks.pop(task_index)
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