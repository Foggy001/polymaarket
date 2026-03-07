#!/usr/bin/env python3
"""
Extended Integration Tests for Dota 2 Arbitrage Bot
Tests GSI integration, trading logic, and edge cases
"""

import requests
import json
import time
from datetime import datetime, timezone

class Dota2BotIntegrationTester:
    def __init__(self, base_url: str = "https://polygon-trader-1.preview.emergentagent.com"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.timeout = 30
        
        print(f"🔧 Dota 2 Bot Integration Tester")
        print(f"📡 Base URL: {self.base_url}")
        print("=" * 60)
    
    def send_gsi_data(self, gsi_data: dict) -> tuple[bool, dict]:
        """Send GSI data to the bot"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/gsi",
                json=gsi_data,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                return True, response.json()
            else:
                print(f"❌ GSI Error: {response.status_code} - {response.text}")
                return False, {}
        except Exception as e:
            print(f"❌ GSI Exception: {e}")
            return False, {}
    
    def get_bot_status(self) -> dict:
        """Get current bot status"""
        try:
            response = self.session.get(f"{self.base_url}/api/bot/status")
            if response.status_code == 200:
                return response.json()
            return {}
        except:
            return {}
    
    def start_bot(self) -> bool:
        """Start the bot"""
        try:
            response = self.session.post(f"{self.base_url}/api/bot/start")
            return response.status_code == 200
        except:
            return False
    
    def test_gsi_data_processing(self):
        """Test GSI data processing and game state updates"""
        print(f"\n🎮 Testing GSI Data Processing")
        
        # Test 1: Basic game state
        print(f"\n  📊 Test 1: Basic Game State Update")
        basic_gsi = {
            "map": {
                "matchid": "integration_test_001",
                "clock_time": 300,  # 5 minutes
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "radiant_score": 5,
                "dire_score": 2,
                "roshan_state": "alive"
            },
            "team2": {  # Radiant
                "player1": {"net_worth": 3000},
                "player2": {"net_worth": 2800},
                "player3": {"net_worth": 2500},
                "player4": {"net_worth": 2200},
                "player5": {"net_worth": 2000}
            },
            "team3": {  # Dire
                "player6": {"net_worth": 2500},
                "player7": {"net_worth": 2200},
                "player8": {"net_worth": 2000},
                "player9": {"net_worth": 1800},
                "player10": {"net_worth": 1600}
            }
        }
        
        success, response = self.send_gsi_data(basic_gsi)
        if success:
            print(f"    ✅ GSI data sent successfully")
            
            # Check if bot status updated
            status = self.get_bot_status()
            if status.get("game_state"):
                gs = status["game_state"]
                print(f"    ✓ Match ID: {gs.get('match_id')}")
                print(f"    ✓ Game Time: {gs.get('game_time')}s")
                print(f"    ✓ Gold Advantage: {gs.get('gold_advantage')}")
                print(f"    ✓ Radiant Net Worth: {gs.get('radiant_net_worth')}")
                print(f"    ✓ Dire Net Worth: {gs.get('dire_net_worth')}")
            else:
                print(f"    ❌ Game state not updated")
        else:
            print(f"    ❌ Failed to send GSI data")
        
        # Test 2: Trigger condition simulation
        print(f"\n  🎯 Test 2: Trigger Condition Simulation")
        
        # First, ensure bot is running
        if not self.start_bot():
            print(f"    ❌ Failed to start bot")
            return
        
        # Send scenario that meets trigger conditions:
        # - Gold advantage >= 2000
        # - Recent kills >= 3
        # - Game time >= 5 minutes
        trigger_gsi = {
            "map": {
                "matchid": "integration_test_002",
                "clock_time": 420,  # 7 minutes
                "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
                "radiant_score": 12,  # Higher score indicates recent kills
                "dire_score": 5,
                "roshan_state": "alive"
            },
            "team2": {  # Radiant (leading)
                "player1": {"net_worth": 6000},
                "player2": {"net_worth": 5500},
                "player3": {"net_worth": 5200},
                "player4": {"net_worth": 4800},
                "player5": {"net_worth": 4500}
            },
            "team3": {  # Dire (losing)
                "player6": {"net_worth": 3200},
                "player7": {"net_worth": 3000},
                "player8": {"net_worth": 2800},
                "player9": {"net_worth": 2500},
                "player10": {"net_worth": 2200}
            }
        }
        
        success, response = self.send_gsi_data(trigger_gsi)
        if success:
            print(f"    ✅ Trigger scenario GSI data sent")
            
            # Check if any trades were triggered
            status = self.get_bot_status()
            if status.get("game_state"):
                gs = status["game_state"]
                gold_adv = gs.get("gold_advantage", 0)
                print(f"    ✓ Gold advantage: {gold_adv} (threshold: 2000)")
                
                if abs(gold_adv) >= 2000:
                    print(f"    ✓ Gold advantage condition met")
                else:
                    print(f"    ⚠️ Gold advantage condition not met")
            
            # Check trade logs
            try:
                trades_response = self.session.get(f"{self.base_url}/api/trades?limit=5")
                if trades_response.status_code == 200:
                    trades_data = trades_response.json()
                    recent_trades = trades_data.get("trades", [])
                    print(f"    📊 Recent trades: {len(recent_trades)}")
                    
                    if recent_trades:
                        latest_trade = recent_trades[0]
                        print(f"    ✓ Latest trade: {latest_trade.get('trigger_type')} for {latest_trade.get('team')}")
                        print(f"      Status: {latest_trade.get('status')}")
                else:
                    print(f"    ⚠️ Could not fetch trade logs")
            except Exception as e:
                print(f"    ⚠️ Error checking trades: {e}")
        else:
            print(f"    ❌ Failed to send trigger GSI data")
    
    def test_config_changes(self):
        """Test bot configuration changes"""
        print(f"\n⚙️ Testing Configuration Changes")
        
        # Test lowering thresholds to make triggers easier
        test_config = {
            "gold_advantage_threshold": 1000,
            "kills_threshold": 2,
            "min_game_time": 180,  # 3 minutes
            "bet_amount": 3.0
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/bot/config",
                json=test_config,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"  ✅ Config updated successfully")
                print(f"    New thresholds: Gold={test_config['gold_advantage_threshold']}, Kills={test_config['kills_threshold']}")
                
                # Verify config was applied
                status = self.get_bot_status()
                if status.get("config"):
                    config = status["config"]
                    print(f"    ✓ Applied gold threshold: {config.get('gold_advantage_threshold')}")
                    print(f"    ✓ Applied kills threshold: {config.get('kills_threshold')}")
                else:
                    print(f"    ⚠️ Could not verify config application")
            else:
                print(f"  ❌ Config update failed: {response.status_code}")
        except Exception as e:
            print(f"  ❌ Config update error: {e}")
    
    def test_edge_cases(self):
        """Test edge cases and error handling"""
        print(f"\n🔬 Testing Edge Cases")
        
        # Test 1: Invalid GSI data
        print(f"\n  📝 Test 1: Invalid GSI Data")
        invalid_gsi = {
            "invalid": "data",
            "map": None
        }
        
        success, response = self.send_gsi_data(invalid_gsi)
        if success:
            print(f"    ✅ Invalid GSI handled gracefully")
            print(f"    Response: {response}")
        else:
            print(f"    ❌ Invalid GSI caused error")
        
        # Test 2: Empty GSI data
        print(f"\n  📝 Test 2: Empty GSI Data")
        empty_gsi = {}
        
        success, response = self.send_gsi_data(empty_gsi)
        if success:
            print(f"    ✅ Empty GSI handled gracefully")
        else:
            print(f"    ❌ Empty GSI caused error")
        
        # Test 3: GSI data with missing fields
        print(f"\n  📝 Test 3: Partial GSI Data")
        partial_gsi = {
            "map": {
                "matchid": "partial_test",
                "clock_time": 100
                # Missing other fields
            }
        }
        
        success, response = self.send_gsi_data(partial_gsi)
        if success:
            print(f"    ✅ Partial GSI handled gracefully")
        else:
            print(f"    ❌ Partial GSI caused error")
    
    def test_polymarket_integration(self):
        """Test Polymarket API integration"""
        print(f"\n💰 Testing Polymarket Integration")
        
        # Test balance endpoint
        try:
            balance_response = self.session.get(f"{self.base_url}/api/balance")
            if balance_response.status_code == 200:
                balance_data = balance_response.json()
                print(f"  ✅ Balance API working")
                print(f"    Balance: {balance_data.get('balance')}")
                print(f"    Allowances: {balance_data.get('allowances')}")
            else:
                print(f"  ❌ Balance API error: {balance_response.status_code}")
        except Exception as e:
            print(f"  ❌ Balance API exception: {e}")
        
        # Test markets endpoint
        try:
            markets_response = self.session.get(f"{self.base_url}/api/markets/dota2")
            if markets_response.status_code == 200:
                markets_data = markets_response.json()
                markets = markets_data.get("markets", [])
                print(f"  ✅ Markets API working")
                print(f"    Found {len(markets)} Dota 2 markets")
                
                if markets:
                    sample_market = markets[0]
                    print(f"    Sample market: {sample_market.get('question', '')[:50]}...")
                    print(f"    Volume 24hr: ${sample_market.get('volume_24hr', 0)}")
                    print(f"    Active: {sample_market.get('active')}")
            else:
                print(f"  ❌ Markets API error: {markets_response.status_code}")
        except Exception as e:
            print(f"  ❌ Markets API exception: {e}")
    
    def run_integration_tests(self):
        """Run all integration tests"""
        print(f"🚀 Starting Integration Tests...\n")
        
        # Test GSI data processing
        self.test_gsi_data_processing()
        
        # Test configuration changes
        self.test_config_changes()
        
        # Test edge cases
        self.test_edge_cases()
        
        # Test Polymarket integration
        self.test_polymarket_integration()
        
        print(f"\n" + "=" * 60)
        print(f"🏁 Integration Tests Complete")
        print(f"=" * 60)


def main():
    """Main integration test execution"""
    tester = Dota2BotIntegrationTester()
    tester.run_integration_tests()


if __name__ == "__main__":
    main()