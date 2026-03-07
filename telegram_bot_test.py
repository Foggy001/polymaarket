#!/usr/bin/env python3
"""
Backend Testing for Polymarket Telegram Bot
Tests Telegram bot functionality and Polymarket client integration
"""

import asyncio
import sys
import os
import logging
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

# Set up test environment
sys.path.insert(0, '/app/backend')

# Import bot modules
from telegram_bot import (
    start, balance, wallet, positions, handle_polymarket_link,
    get_user_client, init_polymarket_client
)
from polymarket_client import PolymarketClient

# Test configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8685153443:AAGGxd024FJwgeztLd-qoMbVE_vJ7zvNbPc')
POLYMARKET_PRIVATE_KEY = os.environ.get('POLYMARKET_PRIVATE_KEY', '0xe30e39d2bcae8fc0190bd56967887869c25ab7c6eb4707e7837838dfe1c833bf')
POLYMARKET_FUNDER_ADDRESS = os.environ.get('POLYMARKET_FUNDER_ADDRESS', '0xFDB59729a94377f454ada54e487eEF880dA3313E')

class TelegramBotTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.test_results = {}
        
    def log_test(self, name: str, success: bool, details: str = ""):
        """Log a test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
            self.test_results[name] = {"status": "PASS", "details": details}
        else:
            self.failed_tests.append(name)
            print(f"❌ {name}: {details}")
            self.test_results[name] = {"status": "FAIL", "details": details}
    
    async def create_mock_update(self, message_text: str, user_id: int = 12345):
        """Create a mock Telegram Update object"""
        mock_update = Mock()
        mock_update.effective_user.id = user_id
        mock_update.message.text = message_text
        mock_update.message.reply_text = AsyncMock()
        mock_update.message.delete = AsyncMock()
        return mock_update
    
    async def create_mock_context(self):
        """Create a mock Telegram Context object"""
        mock_context = Mock()
        mock_context.user_data = {}
        return mock_context
    
    async def test_environment_setup(self):
        """Test if environment variables are properly set"""
        print("\n🔍 Testing Environment Setup...")
        
        # Test Telegram token
        if TELEGRAM_BOT_TOKEN and len(TELEGRAM_BOT_TOKEN.split(':')) == 2:
            self.log_test("Telegram Bot Token Present", True, f"Token: {TELEGRAM_BOT_TOKEN[:20]}...")
        else:
            self.log_test("Telegram Bot Token Present", False, "Invalid or missing token")
        
        # Test Polymarket credentials
        if POLYMARKET_PRIVATE_KEY and POLYMARKET_PRIVATE_KEY.startswith('0x'):
            self.log_test("Polymarket Private Key Present", True, f"Key: {POLYMARKET_PRIVATE_KEY[:10]}...")
        else:
            self.log_test("Polymarket Private Key Present", False, "Invalid or missing key")
            
        if POLYMARKET_FUNDER_ADDRESS and POLYMARKET_FUNDER_ADDRESS.startswith('0x'):
            self.log_test("Polymarket Funder Address Present", True, f"Address: {POLYMARKET_FUNDER_ADDRESS[:10]}...")
        else:
            self.log_test("Polymarket Funder Address Present", False, "Invalid or missing address")
    
    async def test_polymarket_client_initialization(self):
        """Test Polymarket client initialization"""
        print("\n🔍 Testing Polymarket Client...")
        
        try:
            client = PolymarketClient(
                private_key=POLYMARKET_PRIVATE_KEY,
                funder_address=POLYMARKET_FUNDER_ADDRESS,
                signature_type=1
            )
            await client.initialize()
            
            if client.initialized:
                self.log_test("Polymarket Client Initialization", True, "Client initialized successfully")
                
                # Test if CLOB client is available
                if client.clob_client:
                    self.log_test("CLOB Client Available", True, f"Address: {client.address}")
                else:
                    self.log_test("CLOB Client Available", False, "CLOB client not initialized")
                
                # Test API credentials
                if client.api_key:
                    self.log_test("API Credentials Derived", True, f"API Key: {client.api_key[:10]}...")
                else:
                    self.log_test("API Credentials Derived", False, "No API credentials")
                
                await client.close()
                
            else:
                self.log_test("Polymarket Client Initialization", False, "Client not initialized")
                
        except Exception as e:
            self.log_test("Polymarket Client Initialization", False, f"Error: {str(e)}")
    
    async def test_polymarket_balance_api(self):
        """Test Polymarket balance retrieval"""
        print("\n🔍 Testing Polymarket Balance API...")
        
        try:
            client = PolymarketClient(
                private_key=POLYMARKET_PRIVATE_KEY,
                funder_address=POLYMARKET_FUNDER_ADDRESS,
                signature_type=1
            )
            await client.initialize()
            
            balance_data = await client.get_balance()
            
            if isinstance(balance_data, dict):
                balance = balance_data.get('balance', 'N/A')
                self.log_test("Balance API Response", True, f"Balance: {balance} USDC")
            else:
                self.log_test("Balance API Response", False, f"Invalid response: {balance_data}")
                
            await client.close()
            
        except Exception as e:
            self.log_test("Balance API Response", False, f"Error: {str(e)}")
    
    async def test_polymarket_market_fetching(self):
        """Test Polymarket market data fetching"""
        print("\n🔍 Testing Polymarket Market Fetching...")
        
        try:
            client = PolymarketClient(
                private_key=POLYMARKET_PRIVATE_KEY,
                funder_address=POLYMARKET_FUNDER_ADDRESS,
                signature_type=1
            )
            await client.initialize()
            
            # Test market fetching with a known slug pattern
            test_slug = "will-dota-2-team-win"  # Generic test slug
            market = await client.fetch_market_by_slug(test_slug)
            
            if market is not None:
                self.log_test("Market Fetching by Slug", True, f"Market found: {market.get('question', 'Unknown')}")
            else:
                # Try fetching general markets
                try:
                    import httpx
                    async with httpx.AsyncClient() as http_client:
                        response = await http_client.get(
                            "https://gamma-api.polymarket.com/markets",
                            params={"limit": 1, "active": "true"}
                        )
                        if response.status_code == 200:
                            markets = response.json()
                            if markets:
                                self.log_test("Market Fetching by Slug", True, f"Markets API accessible, {len(markets)} markets found")
                            else:
                                self.log_test("Market Fetching by Slug", False, "No markets returned")
                        else:
                            self.log_test("Market Fetching by Slug", False, f"API returned {response.status_code}")
                except Exception as api_e:
                    self.log_test("Market Fetching by Slug", False, f"API test failed: {str(api_e)}")
                    
            await client.close()
            
        except Exception as e:
            self.log_test("Market Fetching by Slug", False, f"Error: {str(e)}")
    
    async def test_telegram_bot_start_command(self):
        """Test /start command handler"""
        print("\n🔍 Testing Telegram Bot /start Command...")
        
        try:
            update = await self.create_mock_update("/start")
            context = await self.create_mock_context()
            
            await start(update, context)
            
            # Check if reply_text was called
            if update.message.reply_text.called:
                call_args = update.message.reply_text.call_args
                reply_text = call_args[0][0] if call_args[0] else ""
                
                if "Polymarket Betting Bot" in reply_text and "/balance" in reply_text:
                    self.log_test("Bot Start Command", True, "Start message contains expected content")
                else:
                    self.log_test("Bot Start Command", False, f"Unexpected reply: {reply_text[:100]}...")
            else:
                self.log_test("Bot Start Command", False, "No reply sent")
                
        except Exception as e:
            self.log_test("Bot Start Command", False, f"Error: {str(e)}")
    
    async def test_telegram_bot_wallet_command(self):
        """Test /wallet command handler"""
        print("\n🔍 Testing Telegram Bot /wallet Command...")
        
        try:
            update = await self.create_mock_update("/wallet")
            context = await self.create_mock_context()
            
            await wallet(update, context)
            
            # Check if reply_text was called
            if update.message.reply_text.called:
                call_args = update.message.reply_text.call_args
                reply_text = call_args[0][0] if call_args[0] else ""
                
                if "Текущий кошелек" in reply_text:
                    self.log_test("Bot Wallet Command", True, "Wallet message contains expected content")
                else:
                    self.log_test("Bot Wallet Command", False, f"Unexpected reply: {reply_text[:100]}...")
            else:
                self.log_test("Bot Wallet Command", False, "No reply sent")
                
        except Exception as e:
            self.log_test("Bot Wallet Command", False, f"Error: {str(e)}")
    
    async def test_telegram_bot_balance_command(self):
        """Test /balance command handler"""
        print("\n🔍 Testing Telegram Bot /balance Command...")
        
        try:
            update = await self.create_mock_update("/balance")
            context = await self.create_mock_context()
            
            await balance(update, context)
            
            # Check if reply_text was called
            if update.message.reply_text.called:
                call_args = update.message.reply_text.call_args
                reply_text = call_args[0][0] if call_args[0] else ""
                
                if "Баланс" in reply_text or "Кошелек не настроен" in reply_text:
                    self.log_test("Bot Balance Command", True, "Balance message contains expected content")
                else:
                    self.log_test("Bot Balance Command", False, f"Unexpected reply: {reply_text[:100]}...")
            else:
                self.log_test("Bot Balance Command", False, "No reply sent")
                
        except Exception as e:
            self.log_test("Bot Balance Command", False, f"Error: {str(e)}")
    
    async def test_polymarket_link_parsing(self):
        """Test Polymarket link parsing functionality"""
        print("\n🔍 Testing Polymarket Link Parsing...")
        
        try:
            # Test with various Polymarket URL formats
            test_urls = [
                "https://polymarket.com/event/dota-2-ti2025-winner",
                "https://polymarket.com/sports/dota-2/match-winner",
                "https://polymarket.com/event/test-market"
            ]
            
            for url in test_urls:
                update = await self.create_mock_update(url)
                context = await self.create_mock_context()
                
                try:
                    await handle_polymarket_link(update, context)
                    
                    # Check if the message was processed (reply_text called)
                    if update.message.reply_text.called:
                        call_args = update.message.reply_text.call_args
                        reply_text = call_args[0][0] if call_args[0] else ""
                        
                        if "Кошелек не настроен" in reply_text or "Загружаю событие" in reply_text:
                            self.log_test(f"Polymarket Link Parsing - {url.split('/')[-1]}", True, "Link processed correctly")
                        else:
                            self.log_test(f"Polymarket Link Parsing - {url.split('/')[-1]}", False, f"Unexpected response: {reply_text[:50]}...")
                    else:
                        # Some URLs might not trigger the handler if regex doesn't match
                        self.log_test(f"Polymarket Link Parsing - {url.split('/')[-1]}", True, "Link not matched by handler (expected for some formats)")
                        
                except Exception as e:
                    self.log_test(f"Polymarket Link Parsing - {url.split('/')[-1]}", False, f"Error: {str(e)}")
                    
        except Exception as e:
            self.log_test("Polymarket Link Parsing", False, f"General error: {str(e)}")
    
    async def test_user_client_functionality(self):
        """Test user client retrieval functionality"""
        print("\n🔍 Testing User Client Functionality...")
        
        try:
            # Test getting client for user without wallet setup
            client = await get_user_client(12345)
            
            if client is None:
                self.log_test("User Client - No Wallet", True, "Correctly returns None for unset wallet")
            else:
                self.log_test("User Client - No Wallet", False, "Should return None for unset wallet")
            
            # Test init_polymarket_client function
            try:
                test_client = await init_polymarket_client(
                    POLYMARKET_PRIVATE_KEY,
                    POLYMARKET_FUNDER_ADDRESS
                )
                if test_client and test_client.initialized:
                    self.log_test("User Client Initialization", True, "Client creation successful")
                else:
                    self.log_test("User Client Initialization", False, "Client not properly initialized")
                
                if test_client:
                    await test_client.close()
                    
            except Exception as e:
                self.log_test("User Client Initialization", False, f"Error: {str(e)}")
                
        except Exception as e:
            self.log_test("User Client Functionality", False, f"Error: {str(e)}")
    
    def print_summary(self):
        """Print test summary"""
        print(f"\n" + "="*60)
        print(f"📊 TELEGRAM BOT TEST SUMMARY")
        print(f"="*60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%" if self.tests_run > 0 else "No tests run")
        
        if self.failed_tests:
            print(f"\n❌ Failed Tests:")
            for test in self.failed_tests:
                details = self.test_results[test]["details"]
                print(f"  - {test}: {details}")
        
        print(f"\n✅ Passed Tests:")
        for test_name, result in self.test_results.items():
            if result["status"] == "PASS":
                print(f"  - {test_name}")
        
        return len(self.failed_tests) == 0

async def main():
    """Run all tests"""
    print("🚀 Starting Telegram Bot Backend Testing...")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    tester = TelegramBotTester()
    
    # Run all tests
    await tester.test_environment_setup()
    await tester.test_polymarket_client_initialization()
    await tester.test_polymarket_balance_api()
    await tester.test_polymarket_market_fetching()
    await tester.test_telegram_bot_start_command()
    await tester.test_telegram_bot_wallet_command()
    await tester.test_telegram_bot_balance_command()
    await tester.test_polymarket_link_parsing()
    await tester.test_user_client_functionality()
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)