#!/usr/bin/env python3
"""
Live Telegram Bot Testing
Tests actual bot responsiveness via Telegram API
"""

import asyncio
import sys
import os
import logging
from datetime import datetime
import httpx

# Test configuration  
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8685153443:AAGGxd024FJwgeztLd-qoMbVE_vJ7zvNbPc')

class LiveTelegramBotTester:
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        
    def log_test(self, name: str, success: bool, details: str = ""):
        """Log a test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            self.failed_tests.append(name)
            print(f"❌ {name}: {details}")
    
    async def test_bot_api_connection(self):
        """Test if bot can connect to Telegram API"""
        print("\n🔍 Testing Bot API Connection...")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/getMe")
                
                if response.status_code == 200:
                    bot_info = response.json()
                    if bot_info.get('ok'):
                        bot_data = bot_info.get('result', {})
                        bot_name = bot_data.get('username', 'Unknown')
                        self.log_test("Bot API Connection", True, f"Bot username: @{bot_name}")
                    else:
                        self.log_test("Bot API Connection", False, f"API error: {bot_info}")
                else:
                    self.log_test("Bot API Connection", False, f"HTTP {response.status_code}")
                    
        except Exception as e:
            self.log_test("Bot API Connection", False, f"Connection error: {str(e)}")
    
    async def test_webhook_status(self):
        """Check webhook information"""
        print("\n🔍 Testing Webhook Status...")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/getWebhookInfo")
                
                if response.status_code == 200:
                    webhook_info = response.json()
                    if webhook_info.get('ok'):
                        webhook_data = webhook_info.get('result', {})
                        url = webhook_data.get('url', '')
                        
                        if url:
                            self.log_test("Webhook Status", True, f"Webhook URL: {url}")
                        else:
                            self.log_test("Webhook Status", True, "No webhook (polling mode)")
                    else:
                        self.log_test("Webhook Status", False, f"API error: {webhook_info}")
                else:
                    self.log_test("Webhook Status", False, f"HTTP {response.status_code}")
                    
        except Exception as e:
            self.log_test("Webhook Status", False, f"Error: {str(e)}")
    
    async def test_updates_polling(self):
        """Check if bot can poll for updates"""
        print("\n🔍 Testing Updates Polling...")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get updates with limit=1 to check if API works
                response = await client.get(
                    f"{self.base_url}/getUpdates",
                    params={"limit": 1, "timeout": 5}
                )
                
                if response.status_code == 200:
                    updates = response.json()
                    if updates.get('ok'):
                        update_list = updates.get('result', [])
                        self.log_test("Updates Polling", True, f"Can poll updates: {len(update_list)} updates")
                    else:
                        self.log_test("Updates Polling", False, f"API error: {updates}")
                else:
                    self.log_test("Updates Polling", False, f"HTTP {response.status_code}")
                    
        except Exception as e:
            self.log_test("Updates Polling", False, f"Error: {str(e)}")
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n" + "="*60)
        print(f"📊 LIVE TELEGRAM BOT TEST SUMMARY")
        print(f"="*60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%" if self.tests_run > 0 else "No tests run")
        
        if self.failed_tests:
            print(f"\n❌ Failed Tests:")
            for test in self.failed_tests:
                print(f"  - {test}")
        
        return len(self.failed_tests) == 0

async def main():
    """Run all live tests"""
    print("🚀 Starting Live Telegram Bot Testing...")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    tester = LiveTelegramBotTester()
    
    # Run all tests
    await tester.test_bot_api_connection()
    await tester.test_webhook_status()
    await tester.test_updates_polling()
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)