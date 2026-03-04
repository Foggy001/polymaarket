#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for Dota 2 Arbitrage Bot
Tests all endpoints as specified in the review request
"""

import requests
import json
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class Dota2BotAPITester:
    def __init__(self, base_url: str = "https://dota2-arbitrage-bot.preview.emergentagent.com"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.timeout = 30
        
        # Test tracking
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        
        print(f"🤖 Dota 2 Arbitrage Bot API Tester")
        print(f"📡 Base URL: {self.base_url}")
        print("=" * 60)
    
    def run_test(self, name: str, method: str, endpoint: str, expected_status: int, 
                 data: Optional[Dict] = None, headers: Optional[Dict] = None) -> tuple[bool, Dict]:
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        if headers is None:
            headers = {'Content-Type': 'application/json'}
        
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        print(f"   {method} {endpoint}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = self.session.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Check status code
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                print(f"   ✅ Status: {response.status_code} (Expected: {expected_status})")
            else:
                print(f"   ❌ Status: {response.status_code} (Expected: {expected_status})")
                self.failed_tests.append({
                    'test': name,
                    'endpoint': endpoint,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:200]
                })
            
            # Try to parse JSON response
            try:
                response_json = response.json()
                print(f"   📝 Response keys: {list(response_json.keys()) if isinstance(response_json, dict) else type(response_json)}")
                return success, response_json
            except json.JSONDecodeError:
                print(f"   📝 Response (non-JSON): {response.text[:100]}...")
                return success, {"raw_response": response.text}
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request failed: {str(e)}")
            self.failed_tests.append({
                'test': name,
                'endpoint': endpoint,
                'error': str(e)
            })
            return False, {"error": str(e)}
    
    def test_health_endpoint(self):
        """Test GET /api/health - API health check"""
        success, response = self.run_test(
            "API Health Check",
            "GET",
            "/api/health",
            200
        )
        
        if success and isinstance(response, dict):
            # Validate expected fields
            expected_fields = ["status", "bot_running", "gsi_connected", "polymarket_connected", "timestamp"]
            for field in expected_fields:
                if field in response:
                    print(f"   ✓ Found field: {field} = {response[field]}")
                else:
                    print(f"   ⚠️ Missing field: {field}")
        
        return success, response
    
    def test_balance_endpoint(self):
        """Test GET /api/balance - Polymarket balance"""
        success, response = self.run_test(
            "Polymarket Balance",
            "GET", 
            "/api/balance",
            200
        )
        
        if success and isinstance(response, dict):
            # Check for balance and allowances
            if "balance" in response or "allowance" in response:
                print(f"   ✓ Balance data found")
                if "balance" in response:
                    print(f"     Balance: {response['balance']}")
                if "allowance" in response:
                    print(f"     Allowance: {response['allowance']}")
            else:
                print(f"   ⚠️ No balance/allowance data found")
        
        return success, response
    
    def test_bot_start(self):
        """Test POST /api/bot/start - Start the bot"""
        success, response = self.run_test(
            "Start Bot",
            "POST",
            "/api/bot/start",
            200
        )
        
        if success and isinstance(response, dict):
            if response.get("status") == "started" or response.get("status") == "already_running":
                print(f"   ✓ Bot start response: {response.get('status')}")
            else:
                print(f"   ⚠️ Unexpected status: {response.get('status')}")
        
        return success, response
    
    def test_bot_stop(self):
        """Test POST /api/bot/stop - Stop the bot"""
        success, response = self.run_test(
            "Stop Bot",
            "POST",
            "/api/bot/stop", 
            200
        )
        
        if success and isinstance(response, dict):
            if response.get("status") == "stopped":
                print(f"   ✓ Bot stopped successfully")
            else:
                print(f"   ⚠️ Unexpected stop status: {response.get('status')}")
        
        return success, response
    
    def test_bot_status(self):
        """Test GET /api/bot/status - Get bot status with game_state"""
        success, response = self.run_test(
            "Bot Status",
            "GET",
            "/api/bot/status",
            200
        )
        
        if success and isinstance(response, dict):
            # Check for expected status fields
            expected_fields = ["is_running", "config", "game_state"]
            for field in expected_fields:
                if field in response:
                    print(f"   ✓ Status field: {field}")
                    if field == "game_state" and response[field]:
                        print(f"     Game state data available")
                else:
                    print(f"   ⚠️ Missing status field: {field}")
        
        return success, response
    
    def test_bot_config_update(self):
        """Test POST /api/bot/config - Update bot configuration"""
        config_data = {
            "gold_advantage_threshold": 2500,
            "kills_threshold": 4,
            "min_game_time": 360,
            "bet_amount": 6.0
        }
        
        success, response = self.run_test(
            "Update Bot Config",
            "POST",
            "/api/bot/config",
            200,
            data=config_data
        )
        
        if success and isinstance(response, dict):
            if response.get("status") == "success":
                print(f"   ✓ Config updated successfully")
                if "config" in response:
                    print(f"     New config applied")
            else:
                print(f"   ⚠️ Config update status: {response.get('status')}")
        
        return success, response
    
    def test_gsi_endpoint(self):
        """Test POST /api/gsi - Send GSI data to update game_state"""
        # Sample GSI data structure
        gsi_data = {
            "map": {
                "matchid": "test_match_123",
                "clock_time": 420,  # 7 minutes
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "radiant_score": 8,
                "dire_score": 5,
                "roshan_state": "alive",
                "roshan_state_end_seconds": 0
            },
            "team2": {  # Radiant players
                "player1": {"net_worth": 5200},
                "player2": {"net_worth": 4800},
                "player3": {"net_worth": 4600},
                "player4": {"net_worth": 4200},
                "player5": {"net_worth": 3900}
            },
            "team3": {  # Dire players
                "player6": {"net_worth": 3500},
                "player7": {"net_worth": 3200},
                "player8": {"net_worth": 3100},
                "player9": {"net_worth": 2900},
                "player10": {"net_worth": 2700}
            }
        }
        
        success, response = self.run_test(
            "Send GSI Data",
            "POST",
            "/api/gsi",
            200,
            data=gsi_data
        )
        
        if success and isinstance(response, dict):
            if response.get("status") == "received":
                print(f"   ✓ GSI data processed successfully")
            else:
                print(f"   ⚠️ GSI status: {response.get('status')}")
        
        # After sending GSI data, check if bot status reflects the update
        print(f"   🔄 Checking if game_state was updated...")
        time.sleep(1)  # Brief delay
        status_success, status_response = self.test_bot_status()
        
        if status_success and status_response.get("game_state"):
            print(f"   ✓ Game state updated in bot status")
            game_state = status_response["game_state"]
            if game_state.get("match_id") == "test_match_123":
                print(f"     ✓ Match ID matches: {game_state['match_id']}")
            if game_state.get("game_time") == 420:
                print(f"     ✓ Game time matches: {game_state['game_time']}s")
        else:
            print(f"   ⚠️ Game state not updated in bot status")
        
        return success, response
    
    def test_dota2_markets(self):
        """Test GET /api/markets/dota2 - Get Dota 2 markets"""
        success, response = self.run_test(
            "Get Dota 2 Markets",
            "GET",
            "/api/markets/dota2",
            200
        )
        
        if success and isinstance(response, dict):
            if "markets" in response:
                markets = response["markets"]
                print(f"   ✓ Found {len(markets)} markets")
                if markets and len(markets) > 0:
                    # Show first market details
                    first_market = markets[0]
                    print(f"     Sample market: {first_market.get('question', 'N/A')[:60]}...")
                    print(f"     Market ID: {first_market.get('slug', 'N/A')}")
                else:
                    print(f"   📝 No Dota 2 markets currently available")
            else:
                print(f"   ⚠️ No 'markets' field in response")
        
        return success, response
    
    def run_all_tests(self):
        """Run all test endpoints in sequence"""
        print(f"🚀 Starting comprehensive API tests...\n")
        
        # Test 1: Health check
        self.test_health_endpoint()
        
        # Test 2: Balance
        self.test_balance_endpoint()
        
        # Test 3: Bot start
        self.test_bot_start()
        
        # Test 4: Bot stop  
        self.test_bot_stop()
        
        # Test 5: Bot status
        self.test_bot_status()
        
        # Test 6: Bot config update
        self.test_bot_config_update()
        
        # Test 7: GSI endpoint (important - should update game_state)
        self.test_gsi_endpoint()
        
        # Test 8: Dota 2 markets
        self.test_dota2_markets()
        
        # Print final results
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 60)
        print(f"📊 TEST SUMMARY")
        print(f"   Total Tests: {self.tests_run}")
        print(f"   Passed: {self.tests_passed}")
        print(f"   Failed: {len(self.failed_tests)}")
        print(f"   Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print(f"\n❌ FAILED TESTS:")
            for i, failure in enumerate(self.failed_tests, 1):
                print(f"   {i}. {failure['test']}")
                print(f"      Endpoint: {failure.get('endpoint', 'N/A')}")
                if 'expected' in failure:
                    print(f"      Expected: {failure['expected']}, Got: {failure['actual']}")
                if 'error' in failure:
                    print(f"      Error: {failure['error']}")
                print()
        else:
            print(f"\n🎉 ALL TESTS PASSED!")
        
        print("=" * 60)


def main():
    """Main test execution"""
    tester = Dota2BotAPITester()
    tester.run_all_tests()
    
    # Return exit code based on results
    return 0 if len(tester.failed_tests) == 0 else 1


if __name__ == "__main__":
    exit(main())