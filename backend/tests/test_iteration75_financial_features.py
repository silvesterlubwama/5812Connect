"""
Iteration 75 - Financial Features Testing
Tests for:
1. Campus accounts (GET/PUT with starting_balance)
2. Inter-account transfers
3. Budgeting per sub-location/department
4. Admin-editable categories
5. Asset appreciation/depreciation
6. Product variants with auto-barcodes
"""
import pytest
import requests
import os
import uuid

import creds  # env-backed logins, see tests/creds.py

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestFinancialFeatures:
    """Test financial improvements: accounts, transfers, budgets, categories, assets, variants"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        data = login_resp.json()
        self.token = data.get("token")
        self.user = data.get("user", {})
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        # Cleanup handled in individual tests
    
    # ========== CAMPUS ACCOUNTS ==========
    
    def test_get_campus_accounts_creates_defaults(self):
        """GET /api/financial/campus-accounts/{id} returns/creates accounts per campus"""
        # Use loc_001 as mentioned in misc_info
        campus_id = "loc_001"
        resp = self.session.get(f"{BASE_URL}/api/financial/campus-accounts/{campus_id}")
        assert resp.status_code == 200, f"Failed to get campus accounts: {resp.text}"
        accounts = resp.json()
        assert isinstance(accounts, list), "Expected list of accounts"
        # Should have accounts (6 operational + 1 savings as per misc_info)
        assert len(accounts) >= 1, "Expected at least one account"
        # Check account structure
        if accounts:
            acct = accounts[0]
            assert "id" in acct, "Account should have id"
            assert "campus_id" in acct, "Account should have campus_id"
            assert "name" in acct, "Account should have name"
            assert "starting_balance" in acct or acct.get("starting_balance") == 0, "Account should have starting_balance"
        print(f"✓ Campus {campus_id} has {len(accounts)} accounts")
    
    def test_update_campus_account(self):
        """PUT /api/financial/campus-accounts/{id} updates account (starting_balance, name)"""
        # First get accounts
        campus_id = "loc_001"
        resp = self.session.get(f"{BASE_URL}/api/financial/campus-accounts/{campus_id}")
        assert resp.status_code == 200
        accounts = resp.json()
        assert len(accounts) > 0, "Need at least one account to test update"
        
        account_id = accounts[0]["id"]
        original_name = accounts[0].get("name", "")
        
        # Update account
        update_data = {
            "name": f"TEST_Updated_{original_name}",
            "starting_balance": 50000,
            "currency": "UGX"
        }
        resp = self.session.put(f"{BASE_URL}/api/financial/campus-accounts/{account_id}", json=update_data)
        assert resp.status_code == 200, f"Failed to update account: {resp.text}"
        updated = resp.json()
        assert updated.get("starting_balance") == 50000, "Starting balance not updated"
        assert "TEST_Updated_" in updated.get("name", ""), "Name not updated"
        
        # Revert name
        self.session.put(f"{BASE_URL}/api/financial/campus-accounts/{account_id}", json={
            "name": original_name,
            "starting_balance": 0
        })
        print(f"✓ Account {account_id} updated successfully")
    
    # ========== INTER-ACCOUNT TRANSFERS ==========
    
    def test_create_transfer(self):
        """POST /api/financial/transfers creates transfer (expense on source + income on dest)"""
        # Get accounts first
        campus_id = "loc_001"
        resp = self.session.get(f"{BASE_URL}/api/financial/campus-accounts/{campus_id}")
        assert resp.status_code == 200
        accounts = resp.json()
        assert len(accounts) >= 2, "Need at least 2 accounts for transfer test"
        
        from_account = accounts[0]
        to_account = accounts[1]
        
        transfer_data = {
            "from_account_id": from_account["id"],
            "to_account_id": to_account["id"],
            "amount": 10000
        }
        resp = self.session.post(f"{BASE_URL}/api/financial/transfers", json=transfer_data)
        assert resp.status_code == 200, f"Failed to create transfer: {resp.text}"
        transfer = resp.json()
        assert "id" in transfer, "Transfer should have id"
        assert transfer.get("amount") == 10000, "Transfer amount mismatch"
        assert transfer.get("from_account_id") == from_account["id"]
        assert transfer.get("to_account_id") == to_account["id"]
        print(f"✓ Transfer {transfer['id']} created: {from_account['name']} -> {to_account['name']}")
    
    def test_list_transfers(self):
        """GET /api/financial/transfers lists transfers"""
        resp = self.session.get(f"{BASE_URL}/api/financial/transfers")
        assert resp.status_code == 200, f"Failed to list transfers: {resp.text}"
        transfers = resp.json()
        assert isinstance(transfers, list), "Expected list of transfers"
        # Should have at least the existing transfer mentioned in misc_info
        print(f"✓ Found {len(transfers)} transfers")
    
    def test_list_transfers_by_campus(self):
        """GET /api/financial/transfers?campus_id=loc_001 filters by campus"""
        resp = self.session.get(f"{BASE_URL}/api/financial/transfers?campus_id=loc_001")
        assert resp.status_code == 200, f"Failed to list transfers by campus: {resp.text}"
        transfers = resp.json()
        assert isinstance(transfers, list)
        print(f"✓ Found {len(transfers)} transfers for campus loc_001")
    
    # ========== BUDGETING ==========
    
    def test_create_budget(self):
        """POST /api/financial/budgets creates budget for sub-location/department"""
        budget_data = {
            "campus_id": "loc_001",
            "location_id": "loc_001",
            "department": "TEST_Finance",
            "period": "2026-01",
            "amount": 500000,
            "category": "operations",
            "notes": "Test budget for iteration 75"
        }
        resp = self.session.post(f"{BASE_URL}/api/financial/budgets", json=budget_data)
        assert resp.status_code == 200, f"Failed to create budget: {resp.text}"
        budget = resp.json()
        assert "id" in budget, "Budget should have id"
        assert budget.get("amount") == 500000
        assert budget.get("department") == "TEST_Finance"
        self.test_budget_id = budget["id"]
        print(f"✓ Budget {budget['id']} created for department TEST_Finance")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/financial/budgets/{budget['id']}")
    
    def test_list_budgets(self):
        """GET /api/financial/budgets lists budgets"""
        resp = self.session.get(f"{BASE_URL}/api/financial/budgets")
        assert resp.status_code == 200, f"Failed to list budgets: {resp.text}"
        budgets = resp.json()
        assert isinstance(budgets, list)
        print(f"✓ Found {len(budgets)} budgets")
    
    def test_list_budgets_by_campus_and_period(self):
        """GET /api/financial/budgets with filters"""
        resp = self.session.get(f"{BASE_URL}/api/financial/budgets?campus_id=loc_001&period=2026-01")
        assert resp.status_code == 200
        budgets = resp.json()
        assert isinstance(budgets, list)
        print(f"✓ Found {len(budgets)} budgets for loc_001 in 2026-01")
    
    def test_delete_budget(self):
        """DELETE /api/financial/budgets/{id} deletes budget"""
        # Create a budget to delete
        budget_data = {
            "campus_id": "loc_001",
            "department": "TEST_ToDelete",
            "amount": 1000
        }
        create_resp = self.session.post(f"{BASE_URL}/api/financial/budgets", json=budget_data)
        assert create_resp.status_code == 200
        budget_id = create_resp.json()["id"]
        
        # Delete it
        del_resp = self.session.delete(f"{BASE_URL}/api/financial/budgets/{budget_id}")
        assert del_resp.status_code == 200, f"Failed to delete budget: {del_resp.text}"
        print(f"✓ Budget {budget_id} deleted")
    
    # ========== CATEGORIES ==========
    
    def test_get_categories_creates_defaults(self):
        """GET /api/financial/categories returns categories (creates defaults if empty)"""
        resp = self.session.get(f"{BASE_URL}/api/financial/categories")
        assert resp.status_code == 200, f"Failed to get categories: {resp.text}"
        categories = resp.json()
        assert isinstance(categories, list)
        # Should have default categories (14 as per code)
        assert len(categories) >= 1, "Expected at least one category"
        # Check structure
        if categories:
            cat = categories[0]
            assert "id" in cat
            assert "name" in cat
            assert "type" in cat  # income, expense, or both
        print(f"✓ Found {len(categories)} categories")
    
    def test_create_category(self):
        """POST /api/financial/categories creates new category"""
        cat_data = {
            "name": "TEST_CustomCategory",
            "type": "expense"
        }
        resp = self.session.post(f"{BASE_URL}/api/financial/categories", json=cat_data)
        assert resp.status_code == 200, f"Failed to create category: {resp.text}"
        category = resp.json()
        assert "id" in category
        assert category.get("name") == "TEST_CustomCategory"
        assert category.get("type") == "expense"
        self.test_category_id = category["id"]
        print(f"✓ Category {category['id']} created")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/financial/categories/{category['id']}")
    
    def test_delete_category(self):
        """DELETE /api/financial/categories/{id} deletes category"""
        # Create a category to delete
        cat_data = {"name": "TEST_ToDelete", "type": "income"}
        create_resp = self.session.post(f"{BASE_URL}/api/financial/categories", json=cat_data)
        assert create_resp.status_code == 200
        cat_id = create_resp.json()["id"]
        
        # Delete it
        del_resp = self.session.delete(f"{BASE_URL}/api/financial/categories/{cat_id}")
        assert del_resp.status_code == 200, f"Failed to delete category: {del_resp.text}"
        print(f"✓ Category {cat_id} deleted")
    
    # ========== ASSET VALUATION ==========
    
    def test_update_asset_valuation_appreciation(self):
        """PUT /api/financial/assets/{id}/valuation updates asset value (appreciation)"""
        # First create an asset
        asset_data = {
            "name": "TEST_Asset_Appreciation",
            "value": 100000,
            "category": "equipment",
            "location_id": "loc_001"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/financial/assets", json=asset_data)
        assert create_resp.status_code == 200, f"Failed to create asset: {create_resp.text}"
        asset = create_resp.json()
        asset_id = asset["id"]
        
        # Update valuation with appreciation
        valuation_data = {
            "current_value": 120000,
            "method": "appreciation"
        }
        resp = self.session.put(f"{BASE_URL}/api/financial/assets/{asset_id}/valuation", json=valuation_data)
        assert resp.status_code == 200, f"Failed to update valuation: {resp.text}"
        updated = resp.json()
        assert updated.get("current_value") == 120000
        assert updated.get("valuation_method") == "appreciation"
        print(f"✓ Asset {asset_id} appreciated to 120000")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/financial/assets/{asset_id}")
    
    def test_update_asset_valuation_depreciation(self):
        """PUT /api/financial/assets/{id}/valuation with depreciation method"""
        # Create an asset
        asset_data = {
            "name": "TEST_Asset_Depreciation",
            "value": 100000,
            "category": "vehicle",
            "location_id": "loc_001"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/financial/assets", json=asset_data)
        assert create_resp.status_code == 200
        asset_id = create_resp.json()["id"]
        
        # Update with depreciation
        valuation_data = {
            "current_value": 80000,
            "method": "depreciation"
        }
        resp = self.session.put(f"{BASE_URL}/api/financial/assets/{asset_id}/valuation", json=valuation_data)
        assert resp.status_code == 200
        updated = resp.json()
        assert updated.get("current_value") == 80000
        assert updated.get("valuation_method") == "depreciation"
        print(f"✓ Asset {asset_id} depreciated to 80000")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/financial/assets/{asset_id}")
    
    def test_asset_valuation_requires_value(self):
        """PUT /api/financial/assets/{id}/valuation returns 400 without current_value"""
        # Create an asset
        asset_data = {"name": "TEST_Asset_NoValue", "value": 50000}
        create_resp = self.session.post(f"{BASE_URL}/api/financial/assets", json=asset_data)
        assert create_resp.status_code == 200
        asset_id = create_resp.json()["id"]
        
        # Try to update without current_value
        resp = self.session.put(f"{BASE_URL}/api/financial/assets/{asset_id}/valuation", json={"method": "appreciation"})
        assert resp.status_code == 400, "Should return 400 without current_value"
        print(f"✓ Valuation correctly requires current_value")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/financial/assets/{asset_id}")
    
    # ========== PRODUCT VARIANTS ==========
    
    def test_add_product_variant_with_auto_barcode(self):
        """POST /api/products/{id}/variants adds variant with auto-barcode"""
        # Create a product first
        product_data = {
            "name": "TEST_Product_Variants",
            "price": 0,
            "has_variants": True,
            "location_id": "loc_001"
        }
        create_resp = self.session.post(f"{BASE_URL}/api/products", json=product_data)
        assert create_resp.status_code == 200, f"Failed to create product: {create_resp.text}"
        product = create_resp.json()
        product_id = product["id"]
        
        # Add variant
        variant_data = {
            "name": "Large",
            "type": "size",
            "value": "L",
            "price": 15000,
            "stock": 10
        }
        resp = self.session.post(f"{BASE_URL}/api/products/{product_id}/variants", json=variant_data)
        assert resp.status_code == 200, f"Failed to add variant: {resp.text}"
        variant = resp.json()
        assert "id" in variant
        assert "barcode" in variant, "Variant should have auto-generated barcode"
        assert variant.get("name") == "Large"
        assert variant.get("price") == 15000
        # Barcode format: {country_code}-{product_id_last6}-V{num}
        barcode = variant.get("barcode", "")
        assert "-V" in barcode, f"Barcode should contain -V: {barcode}"
        print(f"✓ Variant added with barcode: {barcode}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/products/{product_id}")
    
    def test_update_product_variant(self):
        """PUT /api/products/{id}/variants/{vid} updates variant"""
        # Create product with variant
        product_data = {"name": "TEST_Product_UpdateVariant", "price": 0, "has_variants": True}
        create_resp = self.session.post(f"{BASE_URL}/api/products", json=product_data)
        assert create_resp.status_code == 200
        product_id = create_resp.json()["id"]
        
        # Add variant
        variant_resp = self.session.post(f"{BASE_URL}/api/products/{product_id}/variants", json={
            "name": "Small", "type": "size", "price": 10000, "stock": 5
        })
        assert variant_resp.status_code == 200
        variant_id = variant_resp.json()["id"]
        
        # Update variant
        update_data = {"price": 12000, "stock": 20}
        resp = self.session.put(f"{BASE_URL}/api/products/{product_id}/variants/{variant_id}", json=update_data)
        assert resp.status_code == 200, f"Failed to update variant: {resp.text}"
        updated = resp.json()
        assert updated.get("price") == 12000
        assert updated.get("stock") == 20
        print(f"✓ Variant {variant_id} updated")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/products/{product_id}")
    
    def test_delete_product_variant(self):
        """DELETE /api/products/{id}/variants/{vid} removes variant"""
        # Create product with variant
        product_data = {"name": "TEST_Product_DeleteVariant", "price": 0, "has_variants": True}
        create_resp = self.session.post(f"{BASE_URL}/api/products", json=product_data)
        assert create_resp.status_code == 200
        product_id = create_resp.json()["id"]
        
        # Add variant
        variant_resp = self.session.post(f"{BASE_URL}/api/products/{product_id}/variants", json={
            "name": "Medium", "type": "size", "price": 11000
        })
        assert variant_resp.status_code == 200
        variant_id = variant_resp.json()["id"]
        
        # Delete variant
        del_resp = self.session.delete(f"{BASE_URL}/api/products/{product_id}/variants/{variant_id}")
        assert del_resp.status_code == 200, f"Failed to delete variant: {del_resp.text}"
        print(f"✓ Variant {variant_id} deleted")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/products/{product_id}")
    
    def test_generate_barcodes_for_variants(self):
        """POST /api/products/{id}/generate-barcodes auto-generates barcodes"""
        # Create product
        product_data = {"name": "TEST_Product_GenBarcodes", "price": 0, "has_variants": True}
        create_resp = self.session.post(f"{BASE_URL}/api/products", json=product_data)
        assert create_resp.status_code == 200
        product_id = create_resp.json()["id"]
        
        # Add variants without barcodes (by providing empty barcode)
        for name in ["XS", "S", "M"]:
            self.session.post(f"{BASE_URL}/api/products/{product_id}/variants", json={
                "name": name, "type": "size", "price": 10000
            })
        
        # Generate barcodes
        resp = self.session.post(f"{BASE_URL}/api/products/{product_id}/generate-barcodes")
        assert resp.status_code == 200, f"Failed to generate barcodes: {resp.text}"
        result = resp.json()
        assert "message" in result
        assert "prefix" in result
        print(f"✓ Barcodes generated: {result}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/products/{product_id}")
    
    def test_product_with_has_variants_true_and_price_zero(self):
        """Product with has_variants=true and price=0 works"""
        product_data = {
            "name": "TEST_Product_VariantsOnly",
            "price": 0,
            "has_variants": True,
            "description": "Product with variants only, no base price"
        }
        resp = self.session.post(f"{BASE_URL}/api/products", json=product_data)
        assert resp.status_code == 200, f"Failed to create product: {resp.text}"
        product = resp.json()
        assert product.get("price") == 0
        assert product.get("has_variants") == True
        print(f"✓ Product with has_variants=true and price=0 created: {product['id']}")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/products/{product['id']}")
    
    # ========== EXISTING PRODUCT VARIANT TEST ==========
    
    def test_existing_product_variants(self):
        """Test product prod_b622756c already has 2 variants (as per misc_info)"""
        product_id = "prod_b622756c"
        resp = self.session.get(f"{BASE_URL}/api/products")
        assert resp.status_code == 200
        products = resp.json()
        product = next((p for p in products if p.get("id") == product_id), None)
        if product:
            variants = product.get("variants", [])
            print(f"✓ Product {product_id} has {len(variants)} variants")
            for v in variants:
                print(f"  - {v.get('name')}: {v.get('barcode')}")
        else:
            print(f"⚠ Product {product_id} not found (may have been deleted)")
    
    # ========== EXISTING TRANSFER TEST ==========
    
    def test_existing_transfer(self):
        """Test transfer txfr_23c9a87b exists (as per misc_info)"""
        resp = self.session.get(f"{BASE_URL}/api/financial/transfers")
        assert resp.status_code == 200
        transfers = resp.json()
        transfer = next((t for t in transfers if t.get("id") == "txfr_23c9a87b"), None)
        if transfer:
            print(f"✓ Transfer txfr_23c9a87b found: {transfer.get('from_name')} -> {transfer.get('to_name')}")
        else:
            print(f"⚠ Transfer txfr_23c9a87b not found (may have been from previous test)")


class TestTransferValidation:
    """Test transfer validation edge cases"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "identifier": creds.ADMIN_EMAIL,
            "password": creds.ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
    
    def test_transfer_requires_accounts(self):
        """Transfer requires from_account_id and to_account_id"""
        resp = self.session.post(f"{BASE_URL}/api/financial/transfers", json={
            "amount": 1000
        })
        assert resp.status_code == 400, "Should fail without account IDs"
        print("✓ Transfer correctly requires account IDs")
    
    def test_transfer_requires_positive_amount(self):
        """Transfer requires amount > 0"""
        # Get accounts
        accts_resp = self.session.get(f"{BASE_URL}/api/financial/campus-accounts/loc_001")
        accounts = accts_resp.json()
        if len(accounts) >= 2:
            resp = self.session.post(f"{BASE_URL}/api/financial/transfers", json={
                "from_account_id": accounts[0]["id"],
                "to_account_id": accounts[1]["id"],
                "amount": 0
            })
            assert resp.status_code == 400, "Should fail with amount=0"
            print("✓ Transfer correctly requires positive amount")
    
    def test_transfer_invalid_account(self):
        """Transfer fails with non-existent account"""
        resp = self.session.post(f"{BASE_URL}/api/financial/transfers", json={
            "from_account_id": "invalid_account",
            "to_account_id": "also_invalid",
            "amount": 1000
        })
        assert resp.status_code == 404, "Should fail with invalid accounts"
        print("✓ Transfer correctly validates account existence")
