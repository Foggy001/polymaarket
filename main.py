import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Change to backend directory
os.chdir(os.path.join(os.path.dirname(__file__), 'backend'))

# Import and run bot
from telegram_bot import main

if __name__ == '__main__':
    main()
