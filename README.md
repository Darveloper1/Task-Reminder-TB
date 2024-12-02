# Task-Reminder-TB
Telegram bot that reminds you of tasks based on i) task due date &amp; ii) frequency of reminders

Initial Draft #1 (27-10-23):
1. Bot will be written in Python
2. Key functionalities include:
    1. Able to create and store concurrent tasks, along with their due dates and reminder frequency
    2. Able to retrieve current date, and down to the hour ideally

Update #2 (02-12-24):
1. Bot written in Python
2. Options: 
    1. telebotForSelf.py: Does not include user_id
    2. telebotForMultiple.py: Includes user_id
    3. tbForMultipleAndTime.py: Same as 2 but user can dictate frequency of update other than /list
3. Key functionalities include:
    1. Create: Users can create new tasks
    2. Read: View tasks and run a cron to get updates on a regular basis (every day, every other day, every week)
    3. Delete: Users can delete tasks and tasks that are past due date are deleted