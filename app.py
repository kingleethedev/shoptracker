from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime, timedelta, date
import numpy as np
import sqlite3
import os
from werkzeug.utils import secure_filename

from database import Database
from models import User

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Create uploads directory
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
db = Database()

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Helper functions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def format_date_for_display(date_value):
    """Safely format date for display"""
    if not date_value:
        return 'N/A'
    
    if isinstance(date_value, datetime):
        return date_value.strftime('%I:%M %p')
    
    if isinstance(date_value, str):
        try:
            # Try parsing different datetime formats
            for fmt in ['%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(date_value, fmt)
                    return dt.strftime('%I:%M %p')
                except ValueError:
                    continue
            # If parsing fails, extract time from string
            if ' ' in date_value:
                return date_value.split(' ')[1][:5]
            return date_value[:5]
        except:
            return str(date_value)[:5]
    
    return str(date_value)[:5]

# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    user_data = db.get_user_by_id(user_id)
    if user_data:
        return User(id=user_data['id'], username=user_data['username'], role=user_data['role'])
    return None

# Context processor
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

# Teardown appcontext
@app.teardown_appcontext
def close_db_connection(exception=None):
    db.close_connection()

# ============ ROUTES ============

# -------- PUBLIC ROUTES --------
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('employee_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter both username and password', 'error')
            return redirect(url_for('login'))
        
        user_data = db.authenticate_user(username, password)
        
        if user_data:
            user = User(id=user_data['id'], username=user_data['username'], role=user_data['role'])
            login_user(user)
            flash('Login successful!', 'success')
            
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# -------- EMPLOYEE ROUTES --------
@app.route('/employee/dashboard')
@login_required
def employee_dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    try:
        # Get products
        products = db.get_all_products()
        
        # Format products for display
        safe_products = []
        for product in products:
            product_dict = dict(product) if not isinstance(product, dict) else product
            
            # Ensure all required fields exist
            product_dict.setdefault('image_filename', None)
            product_dict.setdefault('selling_price', 0)
            product_dict.setdefault('quantity', 0)
            product_dict.setdefault('name', 'Unknown Product')
            
            safe_products.append(product_dict)
        
        # Get recent sales
        recent_sales_data = db.get_all_sales()[:10]
        
        # Format sales for display
        formatted_sales = []
        today_sales = []
        today_str = date.today().isoformat()
        
        for sale in recent_sales_data:
            sale_dict = dict(sale) if not isinstance(sale, dict) else sale
            
            # Format date
            sale_date = sale_dict.get('sale_date', '')
            if isinstance(sale_date, str):
                sale_dict['display_time'] = format_date_for_display(sale_date)
                # Check if today
                if today_str in sale_date:
                    today_sales.append(sale_dict)
            else:
                sale_dict['display_time'] = 'N/A'
            
            formatted_sales.append(sale_dict)
        
        return render_template('employee_dashboard.html',
                             products=safe_products,
                             recent_sales=formatted_sales,
                             today_sales=today_sales)
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('employee_dashboard.html',
                             products=[],
                             recent_sales=[],
                             today_sales=[])

@app.route('/employee/sell', methods=['POST'])
@login_required
def sell_product():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    try:
        product_id = request.form.get('product_id')
        quantity_str = request.form.get('quantity', '0')
        
        # Validate inputs
        if not product_id:
            flash('Please select a product', 'error')
            return redirect(url_for('employee_dashboard'))
        
        try:
            quantity = int(quantity_str)
        except ValueError:
            flash('Invalid quantity', 'error')
            return redirect(url_for('employee_dashboard'))
        
        if quantity <= 0:
            flash('Quantity must be greater than 0', 'error')
            return redirect(url_for('employee_dashboard'))
        
        # Get product
        product = db.get_product_by_id(product_id)
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('employee_dashboard'))
        
        # Check stock
        if product['quantity'] < quantity:
            flash(f'Insufficient stock! Only {product["quantity"]} items available.', 'error')
            return redirect(url_for('employee_dashboard'))
        
        # Calculate sale
        total_price = product['selling_price'] * quantity
        profit = (product['selling_price'] - product['buying_price']) * quantity
        
        # Record sale
        db.record_sale(product_id, quantity, total_price, profit)
        
        flash(f'Sale recorded successfully! Total: KES {total_price:,.2f}', 'success')
        return redirect(url_for('employee_dashboard'))
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('employee_dashboard'))

# ============ NEW EXPENSE MANAGEMENT ROUTES ============

@app.route('/admin/expenses')
@login_required
def admin_expenses():
    """Manage expenses"""
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        # Get all expenses
        expenses = db.get_all_expenses()
        categories = db.get_all_expense_categories()
        
        # Get date range for filtering
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date or end_date:
            expenses = db.get_all_expenses(start_date, end_date)
        
        return render_template('admin_expenses.html',
                             expenses=expenses,
                             categories=categories,
                             start_date=start_date,
                             end_date=end_date)
    except Exception as e:
        flash(f'Error loading expenses: {str(e)}', 'error')
        return render_template('admin_expenses.html',
                             expenses=[],
                             categories=[])

@app.route('/admin/expenses/add', methods=['GET', 'POST'])
@login_required
def admin_add_expense():
    """Add a new expense"""
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        try:
            category_id = request.form.get('category_id')
            amount_str = request.form.get('amount', '0')
            description = request.form.get('description', '').strip()
            
            # Validate
            if not category_id:
                flash('Please select a category', 'error')
                return redirect(url_for('admin_add_expense'))
            
            try:
                amount = float(amount_str)
            except ValueError:
                flash('Invalid amount', 'error')
                return redirect(url_for('admin_add_expense'))
            
            if amount <= 0:
                flash('Amount must be greater than 0', 'error')
                return redirect(url_for('admin_add_expense'))
            
            # Add expense
            db.add_expense(category_id, amount, description)
            flash('Expense added successfully!', 'success')
            return redirect(url_for('admin_expenses'))
            
        except Exception as e:
            flash(f'Error adding expense: {str(e)}', 'error')
            return redirect(url_for('admin_add_expense'))
    
    # GET request - show form
    categories = db.get_all_expense_categories()
    return render_template('admin_add_expense.html', categories=categories)

@app.route('/admin/expenses/delete/<int:expense_id>', methods=['POST'])
@login_required
def admin_delete_expense(expense_id):
    """Delete an expense"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        db.delete_expense(expense_id)
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/expense-categories')
@login_required
def admin_expense_categories():
    """Manage expense categories"""
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        categories = db.get_all_expense_categories()
        return render_template('admin_expense_categories.html', categories=categories)
    except Exception as e:
        flash(f'Error loading categories: {str(e)}', 'error')
        return render_template('admin_expense_categories.html', categories=[])

@app.route('/admin/expense-categories/add', methods=['POST'])
@login_required
def admin_add_expense_category():
    """Add a new expense category"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        name = request.form.get('name', '').strip()
        category_type = request.form.get('type', 'operating')
        
        if not name:
            flash('Category name is required', 'error')
            return redirect(url_for('admin_expense_categories'))
        
        if category_type not in ['operating', 'cogs']:
            category_type = 'operating'
        
        db.add_expense_category(name, category_type)
        flash(f'Category "{name}" added successfully!', 'success')
        return redirect(url_for('admin_expense_categories'))
        
    except Exception as e:
        flash(f'Error adding category: {str(e)}', 'error')
        return redirect(url_for('admin_expense_categories'))

# ============ PROFIT ANALYSIS ROUTES ============

@app.route('/admin/profit-analysis')
@login_required
def admin_profit_analysis():
    """Profit analysis page showing gross and net profit"""
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        # Get date range
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Get profit analysis
        profit_data = db.get_profit_analysis(start_date, end_date)
        
        # Get expenses by category
        expenses_by_category = db.get_expenses_by_category(start_date, end_date)
        
        # Get operating and COGS expenses separately
        operating_expenses = [e for e in expenses_by_category if e['category_type'] == 'operating']
        cogs_expenses = [e for e in expenses_by_category if e['category_type'] == 'cogs']
        
        # Generate profit chart
        profit_chart = generate_profit_chart(profit_data)
        
        # Generate expense chart
        expense_chart = generate_expense_chart(expenses_by_category)
        
        return render_template('admin_profit_analysis.html',
                             profit_data=profit_data,
                             operating_expenses=operating_expenses,
                             cogs_expenses=cogs_expenses,
                             start_date=start_date,
                             end_date=end_date,
                             profit_chart=profit_chart,
                             expense_chart=expense_chart)
        
    except Exception as e:
        flash(f'Error loading profit analysis: {str(e)}', 'error')
        return render_template('admin_profit_analysis.html',
                             profit_data={},
                             operating_expenses=[],
                             cogs_expenses=[])

# ============ UPDATED ADMIN DASHBOARD ============

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        # Get dashboard data
        summary = db.get_sales_summary() or {'total_sales': 0, 'total_revenue': 0, 'total_gross_profit': 0}
        low_stock = db.get_low_stock_products(threshold=10)
        best_selling = db.get_best_selling_products(limit=5)
        recent_sales_data = db.get_all_sales()[:10]
        
        # Get profit analysis for today
        today = date.today().isoformat()
        profit_data = db.get_profit_analysis(today, today)
        
        # Format sales
        formatted_sales = []
        for sale in recent_sales_data:
            sale_dict = dict(sale) if not isinstance(sale, dict) else sale
            sale_dict['display_time'] = format_date_for_display(sale_dict.get('sale_date'))
            formatted_sales.append(sale_dict)
        
        # Get product stats
        products = db.get_all_products()
        total_products = len(products)
        total_items = sum(p.get('quantity', 0) for p in products)
        
        # Get recent expenses
        recent_expenses = db.get_all_expenses()[:5]
        
        return render_template('admin_dashboard.html',
                             summary=summary,
                             profit_data=profit_data,
                             low_stock=low_stock,
                             best_selling=best_selling,
                             recent_sales=formatted_sales,
                             recent_expenses=recent_expenses,
                             total_products=total_products,
                             total_items=total_items)
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('admin_dashboard.html',
                             summary={'total_sales': 0, 'total_revenue': 0, 'total_gross_profit': 0},
                             profit_data={},
                             low_stock=[],
                             best_selling=[],
                             recent_sales=[],
                             recent_expenses=[],
                             total_products=0,
                             total_items=0)

@app.route('/admin/products')
@login_required
def admin_products():
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        products = db.get_all_products()
        return render_template('admin_products.html', products=products)
    except Exception as e:
        flash(f'Error loading products: {str(e)}', 'error')
        return render_template('admin_products.html', products=[])

@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    if request.method == 'POST':
        try:
            # Get form data
            name = request.form.get('name', '').strip()
            buying_price_str = request.form.get('buying_price', '0')
            selling_price_str = request.form.get('selling_price', '0')
            quantity_str = request.form.get('quantity', '0')
            
            # Validate
            if not name:
                flash('Product name is required', 'error')
                return redirect(url_for('admin_add_product'))
            
            try:
                buying_price = float(buying_price_str)
                selling_price = float(selling_price_str)
                quantity = int(quantity_str)
            except ValueError:
                flash('Invalid price or quantity', 'error')
                return redirect(url_for('admin_add_product'))
            
            if buying_price < 0 or selling_price < 0 or quantity < 0:
                flash('Prices and quantity must be non-negative', 'error')
                return redirect(url_for('admin_add_product'))
            
            if selling_price <= buying_price:
                flash('Selling price must be greater than buying price', 'error')
                return redirect(url_for('admin_add_product'))
            
            # Handle image
            image_filename = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    if allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{timestamp}_{filename}"
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        image_filename = filename
                    else:
                        flash('Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP', 'error')
                        return redirect(url_for('admin_add_product'))
            
            # Add product
            db.add_product(name, buying_price, selling_price, quantity, image_filename)
            flash('Product added successfully!', 'success')
            return redirect(url_for('admin_products'))
            
        except Exception as e:
            flash(f'Error adding product: {str(e)}', 'error')
            return redirect(url_for('admin_add_product'))
    
    return render_template('admin_add_product.html')

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def admin_edit_product(product_id):
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        product = db.get_product_by_id(product_id)
        if not product:
            flash('Product not found', 'error')
            return redirect(url_for('admin_products'))
        
        if request.method == 'POST':
            # Get form data
            name = request.form.get('name', '').strip()
            buying_price_str = request.form.get('buying_price', '0')
            selling_price_str = request.form.get('selling_price', '0')
            quantity_str = request.form.get('quantity', '0')
            
            # Validate
            if not name:
                flash('Product name is required', 'error')
                return redirect(url_for('admin_edit_product', product_id=product_id))
            
            try:
                buying_price = float(buying_price_str)
                selling_price = float(selling_price_str)
                quantity = int(quantity_str)
            except ValueError:
                flash('Invalid price or quantity', 'error')
                return redirect(url_for('admin_edit_product', product_id=product_id))
            
            if buying_price < 0 or selling_price < 0 or quantity < 0:
                flash('Prices and quantity must be non-negative', 'error')
                return redirect(url_for('admin_edit_product', product_id=product_id))
            
            if selling_price <= buying_price:
                flash('Selling price must be greater than buying price', 'error')
                return redirect(url_for('admin_edit_product', product_id=product_id))
            
            # Handle image
            image_filename = product.get('image_filename')
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename:
                    if allowed_file(file.filename):
                        # Delete old image
                        if image_filename:
                            old_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        
                        # Save new image
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{timestamp}_{filename}"
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        image_filename = filename
                    else:
                        flash('Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP', 'error')
                        return redirect(url_for('admin_edit_product', product_id=product_id))
            
            # Update product
            db.update_product(product_id, name, buying_price, selling_price, quantity, image_filename)
            flash('Product updated successfully!', 'success')
            return redirect(url_for('admin_products'))
        
        return render_template('admin_edit_product.html', product=product)
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('admin_products'))

@app.route('/admin/products/delete/<int:product_id>')
@login_required
def admin_delete_product(product_id):
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        db.delete_product(product_id)
        flash('Product deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting product: {str(e)}', 'error')
    
    return redirect(url_for('admin_products'))

@app.route('/admin/reports')
@login_required
def admin_reports():
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        # Get data
        profit_per_product = db.get_profit_per_product()
        daily_trend = db.get_daily_profit_trend(days=30)
        
        # Calculate metrics
        total_revenue = sum(p.get('total_revenue', 0) for p in profit_per_product)
        total_gross_profit = sum(p.get('total_profit', 0) for p in profit_per_product)
        total_items = sum(p.get('total_quantity', 0) for p in profit_per_product)
        
        # Get total expenses for net profit calculation
        total_expenses = db.get_total_expenses()
        net_profit = total_gross_profit - total_expenses
        
        # Averages
        days_count = len(daily_trend) if daily_trend else 30
        daily_avg_revenue = total_revenue / days_count if days_count > 0 else 0
        daily_avg_profit = total_gross_profit / days_count if days_count > 0 else 0
        daily_avg_items = total_items / days_count if days_count > 0 else 0
        
        # Profit margins
        gross_profit_margin = (total_gross_profit / total_revenue * 100) if total_revenue > 0 else 0
        net_profit_margin = (net_profit / total_revenue * 100) if total_revenue > 0 else 0
        
        # Best day
        if daily_trend:
            best_day = max(daily_trend, key=lambda x: x.get('daily_revenue', 0))
            best_day_revenue = best_day.get('daily_revenue', 0)
            best_day_date = best_day.get('date', 'N/A')
        else:
            best_day_revenue = 0
            best_day_date = 'N/A'
        
        # Growth rate
        if daily_trend and len(daily_trend) >= 2:
            first_day = daily_trend[0].get('daily_revenue', 0)
            last_day = daily_trend[-1].get('daily_revenue', 0)
            growth_rate = ((last_day - first_day) / first_day * 100) if first_day > 0 else 0
        else:
            growth_rate = 0
        
        # Top products
        top_products = sorted(profit_per_product,
                            key=lambda x: x.get('total_profit', 0),
                            reverse=True)[:5]
        
        # Generate charts using the generate_charts function from app.py
        charts = generate_charts(profit_per_product, daily_trend, top_products)
        
        return render_template('admin_reports.html',
                             profit_per_product=profit_per_product,
                             top_products=top_products,
                             daily_avg_revenue=daily_avg_revenue,
                             daily_avg_profit=daily_avg_profit,
                             daily_avg_items=daily_avg_items,
                             gross_profit_margin=gross_profit_margin,
                             net_profit_margin=net_profit_margin,
                             net_profit=net_profit,
                             total_expenses=total_expenses,
                             best_day_revenue=best_day_revenue,
                             best_day_date=best_day_date,
                             growth_rate=growth_rate,
                             **charts)
        
    except Exception as e:
        flash(f'Error loading reports: {str(e)}', 'error')
        return render_template('admin_reports.html',
                             profit_per_product=[],
                             top_products=[],
                             daily_avg_revenue=0,
                             daily_avg_profit=0,
                             daily_avg_items=0,
                             gross_profit_margin=0,
                             net_profit_margin=0,
                             net_profit=0,
                             total_expenses=0,
                             best_day_revenue=0,
                             best_day_date='N/A',
                             growth_rate=0,
                             profit_chart='',
                             trend_chart='',
                             distribution_chart='')
    
# -------- UTILITY ROUTES --------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/sales-data')
@login_required
def api_sales_data():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
    
    try:
        daily_trend = db.get_daily_profit_trend(days=7)
        return jsonify(daily_trend)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create-test-data')
def create_test_data():
    """Create test data (for development only)"""
    try:
        # Add test products if none exist
        products = db.get_all_products()
        if not products:
            test_products = [
                ("Sugar 1kg", 100, 120, 50),
                ("Rice 2kg", 200, 250, 30),
                ("Cooking Oil 1L", 300, 350, 20),
                ("Tea Leaves 250g", 150, 180, 40),
                ("Wheat Flour 2kg", 180, 220, 25),
                ("Salt 500g", 50, 70, 60),
            ]
            
            for name, buy, sell, qty in test_products:
                db.add_product(name, buy, sell, qty)
            
            flash('Test products created successfully!', 'success')
        else:
            flash('Products already exist in database', 'info')
        
        return redirect(url_for('login'))
    except Exception as e:
        flash(f'Error creating test data: {str(e)}', 'error')
        return redirect(url_for('login'))

# -------- ERROR HANDLERS --------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# ============ NEW CHART FUNCTIONS ============

def generate_profit_chart(profit_data):
    """Generate profit comparison chart"""
    try:
        fig, ax = plt.subplots(figsize=(8, 6))
        
        categories = ['Revenue', 'Gross Profit', 'Net Profit']
        values = [
            profit_data.get('total_revenue', 0),
            profit_data.get('total_gross_profit', 0),
            profit_data.get('net_profit', 0)
        ]
        
        colors = ['#3498db', '#2ecc71', '#e74c3c']
        bars = ax.bar(categories, values, color=colors)
        
        ax.set_ylabel('Amount (KES)')
        ax.set_title('Profit Analysis')
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            if height != 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'KES {height:,.0f}',
                       ha='center', va='bottom', fontsize=10)
        
        plt.tight_layout()
        img = io.BytesIO()
        plt.savefig(img, format='png', dpi=100, bbox_inches='tight')
        img.seek(0)
        chart = base64.b64encode(img.getvalue()).decode('utf8')
        plt.close(fig)
        
        return chart
    except Exception as e:
        print(f"Error generating profit chart: {e}")
        return ""

def generate_expense_chart(expenses_by_category):
    """Generate expense breakdown chart"""
    try:
        # Filter only categories with expenses
        filtered_expenses = [e for e in expenses_by_category if e.get('total_amount', 0) > 0]
        
        if not filtered_expenses:
            return ""
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        category_names = [e.get('category_name', 'Unknown') for e in filtered_expenses]
        amounts = [e.get('total_amount', 0) for e in filtered_expenses]
        
        # Sort by amount
        sorted_data = sorted(zip(category_names, amounts), key=lambda x: x[1], reverse=True)
        category_names, amounts = zip(*sorted_data) if sorted_data else ([], [])
        
        # Create bar chart
        bars = ax.barh(category_names, amounts, color=plt.cm.Set3(np.linspace(0, 1, len(category_names))))
        
        ax.set_xlabel('Amount (KES)')
        ax.set_title('Expenses by Category')
        
        # Add value labels
        for bar in bars:
            width = bar.get_width()
            if width > 0:
                ax.text(width, bar.get_y() + bar.get_height()/2.,
                       f'KES {width:,.0f}',
                       ha='left', va='center', fontsize=9)
        
        plt.tight_layout()
        img = io.BytesIO()
        plt.savefig(img, format='png', dpi=100, bbox_inches='tight')
        img.seek(0)
        chart = base64.b64encode(img.getvalue()).decode('utf8')
        plt.close(fig)
        
        return chart
    except Exception as e:
        print(f"Error generating expense chart: {e}")
        return ""

# ============ HELPER FUNCTIONS ============

def generate_charts(profit_per_product, daily_trend, top_products):
    """Generate chart images for reports"""
    charts = {
        'profit_chart': '',
        'trend_chart': '',
        'distribution_chart': ''
    }
    
    try:
        # 1. Profit per product chart
        if profit_per_product:
            fig1, ax1 = plt.subplots(figsize=(10, 6))
            product_names = [p.get('product_name', 'Unknown')[:15] for p in profit_per_product[:8]]
            profits = [p.get('total_profit', 0) for p in profit_per_product[:8]]
            
            if profits:
                bars = ax1.bar(range(len(product_names)), profits, color='skyblue')
                ax1.set_xlabel('Products')
                ax1.set_ylabel('Profit (KES)')
                ax1.set_title('Profit per Product')
                ax1.set_xticks(range(len(product_names)))
                ax1.set_xticklabels(product_names, rotation=45, ha='right')
                
                # Add value labels
                for bar in bars:
                    height = bar.get_height()
                    if height > 0:
                        ax1.text(bar.get_x() + bar.get_width()/2., height,
                                f'KES {height:,.0f}',
                                ha='center', va='bottom', fontsize=8)
            
            plt.tight_layout()
            img1 = io.BytesIO()
            plt.savefig(img1, format='png', dpi=100, bbox_inches='tight')
            img1.seek(0)
            charts['profit_chart'] = base64.b64encode(img1.getvalue()).decode('utf8')
            plt.close(fig1)
        
        # 2. Daily trend chart
        if daily_trend:
            fig2, ax2 = plt.subplots(figsize=(12, 6))
            dates = [datetime.strptime(d.get('date', '2000-01-01'), '%Y-%m-%d') for d in daily_trend]
            daily_profits = [d.get('daily_gross_profit', 0) for d in daily_trend]
            
            ax2.plot(dates, daily_profits, marker='o', color='green', linewidth=2)
            ax2.set_xlabel('Date')
            ax2.set_ylabel('Daily Gross Profit (KES)')
            ax2.set_title('Daily Gross Profit Trend (Last 30 Days)')
            ax2.tick_params(axis='x', rotation=45)
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            img2 = io.BytesIO()
            plt.savefig(img2, format='png', dpi=100, bbox_inches='tight')
            img2.seek(0)
            charts['trend_chart'] = base64.b64encode(img2.getvalue()).decode('utf8')
            plt.close(fig2)
        
        # 3. Distribution chart
        if top_products and any(p.get('total_quantity', 0) > 0 for p in top_products):
            fig3, ax3 = plt.subplots(figsize=(8, 8))
            product_names_pie = [p.get('product_name', 'Unknown') for p in top_products 
                               if p.get('total_quantity', 0) > 0]
            quantities = [p.get('total_quantity', 0) for p in top_products 
                         if p.get('total_quantity', 0) > 0]
            
            if product_names_pie:
                colors = plt.cm.Set3(np.linspace(0, 1, len(product_names_pie)))
                wedges, texts, autotexts = ax3.pie(quantities, labels=product_names_pie, 
                                                  autopct='%1.1f%%', colors=colors, startangle=90)
                ax3.set_title('Products Sold Distribution')
            
            plt.tight_layout()
            img3 = io.BytesIO()
            plt.savefig(img3, format='png', dpi=100, bbox_inches='tight')
            img3.seek(0)
            charts['distribution_chart'] = base64.b64encode(img3.getvalue()).decode('utf8')
            plt.close(fig3)
            
    except Exception as e:
        print(f"Error generating charts: {e}")
    
    return charts

# ============ PASSWORD MANAGEMENT ROUTES ============

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow users to change their own password"""
    if request.method == 'POST':
        try:
            current_password = request.form.get('current_password', '').strip()
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            
            # Validate inputs
            if not current_password or not new_password or not confirm_password:
                flash('All password fields are required', 'error')
                return redirect(url_for('change_password'))
            
            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return redirect(url_for('change_password'))
            
            if len(new_password) < 6:
                flash('New password must be at least 6 characters long', 'error')
                return redirect(url_for('change_password'))
            
            # Verify current password
            user_data = db.authenticate_user(current_user.username, current_password)
            if not user_data:
                flash('Current password is incorrect', 'error')
                return redirect(url_for('change_password'))
            
            # Update password
            db.update_user_password(current_user.id, new_password)
            
            flash('Password changed successfully! Please login again with your new password.', 'success')
            logout_user()
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(f'Error changing password: {str(e)}', 'error')
            return redirect(url_for('change_password'))
    
    return render_template('change_password.html')

# ============ ADMIN USER MANAGEMENT ROUTES ============

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin user management page"""
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        users = db.get_all_users()
        return render_template('admin_users.html', users=users)
    except Exception as e:
        flash(f'Error loading users: {str(e)}', 'error')
        return render_template('admin_users.html', users=[])

@app.route('/admin/users/add', methods=['POST'])
@login_required
def add_user():
    """Add a new user (admin only)"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        role = request.form.get('role', 'employee').strip()
        
        # Validate
        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('admin_users'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('admin_users'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect(url_for('admin_users'))
        
        if role not in ['admin', 'employee']:
            role = 'employee'
        
        # Add user
        db.add_user(username, password, role)
        flash(f'User {username} added successfully!', 'success')
        return redirect(url_for('admin_users'))
        
    except Exception as e:
        flash(f'Error adding user: {str(e)}', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/users/reset-password/<int:user_id>', methods=['POST'])
@login_required
def reset_user_password(user_id):
    """Reset user password (admin only)"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        new_password = data.get('new_password', '').strip()
        
        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'})
        
        db.update_user_password(user_id, new_password)
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete a user (admin only)"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        db.delete_user(user_id)
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    
@app.route('/admin/simple-profit', methods=['GET', 'POST'])
@login_required
def simple_profit_calculator():
    """Simple profit calculator for business owners"""
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    # Get profit data for the current month
    today = date.today()
    first_day = today.replace(day=1).isoformat()
    last_day = today.isoformat()
    
    profit_data = db.get_profit_analysis(first_day, last_day)
    
    # Handle POST request (save expenses)
    if request.method == 'POST':
        try:
            # Get category IDs (we need to ensure these categories exist)
            categories = db.get_all_expense_categories()
            
            # Create a mapping of category names to IDs
            category_map = {}
            for cat in categories:
                category_map[cat['name'].lower()] = cat['id']
            
            # Get form data
            data = request.form
            
            # Helper function to save expense
            def save_expense(category_name, amount, description):
                if amount > 0:
                    # Find or create category
                    category_id = None
                    if category_name.lower() in category_map:
                        category_id = category_map[category_name.lower()]
                    else:
                        # Determine category type
                        category_type = 'operating'
                        if 'salary' in category_name.lower() or 'rent' in category_name.lower() or 'utility' in category_name.lower():
                            category_type = 'operating'
                        
                        # Add new category
                        try:
                            category_id = db.add_expense_category(category_name, category_type)
                            category_map[category_name.lower()] = category_id
                        except Exception as e:
                            print(f"Error adding category: {e}")
                            return False
                    
                    # Save expense
                    try:
                        db.add_expense(category_id, amount, description)
                        return True
                    except Exception as e:
                        print(f"Error adding expense: {e}")
                        return False
                return True
            
            # Save each expense category
            expenses_saved = 0
            
            # Rent
            if save_expense('Rent', float(data.get('rent', 0)), 'Monthly shop rent'):
                expenses_saved += 1
            
            # Owner Salary
            if save_expense('Owner Salary', float(data.get('owner_salary', 0)), 'Business owner salary'):
                expenses_saved += 1
            
            # Employee Salaries
            if save_expense('Employee Salaries', float(data.get('employee_salaries', 0)), 'Staff salaries'):
                expenses_saved += 1
            
            # Electricity
            if save_expense('Electricity', float(data.get('electricity', 0)), 'Monthly electricity bill'):
                expenses_saved += 1
            
            # Water
            if save_expense('Water', float(data.get('water', 0)), 'Monthly water bill'):
                expenses_saved += 1
            
            # Transport
            if save_expense('Transport', float(data.get('transport', 0)), 'Transport and logistics costs'):
                expenses_saved += 1
            
            # Advertising
            if save_expense('Advertising', float(data.get('advertising', 0)), 'Marketing and advertising costs'):
                expenses_saved += 1
            
            # Miscellaneous
            misc_amount = float(data.get('miscellaneous', 0))
            if misc_amount > 0:
                if save_expense('Miscellaneous Expenses', misc_amount, 'Other miscellaneous expenses'):
                    expenses_saved += 1
            
            flash(f'{expenses_saved} expense categories saved successfully!', 'success')
            return redirect(url_for('admin_expenses'))
            
        except Exception as e:
            flash(f'Error saving expenses: {str(e)}', 'error')
            return redirect(url_for('simple_profit_calculator'))
    
    # GET request - show calculator
    return render_template('simple_profit.html', profit_data=profit_data)

# ============ DATA RESET ROUTES ============

@app.route('/admin/data-reset')
@login_required
def admin_data_reset():
    """Data reset confirmation page"""
    if not current_user.is_admin:
        return redirect(url_for('employee_dashboard'))
    
    try:
        # Get data counts
        products = db.get_all_products()
        sales = db.get_all_sales()
        expenses = db.get_all_expenses()
        categories = db.get_all_expense_categories()
        
        stats = {
            'products': len(products),
            'sales': len(sales),
            'expenses': len(expenses),
            'categories': len(categories),
            'total_revenue': sum(s.get('total_price', 0) for s in sales),
            'total_expenses': sum(e.get('amount', 0) for e in expenses)
        }
        
        return render_template('admin_data_reset.html', stats=stats)
    except Exception as e:
        flash(f'Error loading data: {str(e)}', 'error')
        return render_template('admin_data_reset.html', stats={})

@app.route('/admin/delete-all-data', methods=['POST'])
@login_required
def delete_all_data():
    """Delete ALL data from database (except users)"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        # Get confirmation from request
        data = request.get_json()
        confirm_text = data.get('confirm_text', '').strip().lower()
        
        if confirm_text != 'delete all data':
            return jsonify({
                'success': False, 
                'error': 'Confirmation text incorrect. Please type "delete all data" exactly.'
            })
        
        # Connect to database directly
        conn = sqlite3.connect('instance/shop.db')
        cursor = conn.cursor()
        
        # Start transaction
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            # Delete data from tables in correct order (respecting foreign keys)
            cursor.execute('DELETE FROM sales')
            cursor.execute('DELETE FROM expenses')
            cursor.execute('DELETE FROM expense_categories')
            cursor.execute('DELETE FROM products')
            
            # Reset auto-increment counters (optional, but good practice)
            cursor.execute('DELETE FROM sqlite_sequence WHERE name IN ("products", "sales", "expenses", "expense_categories")')
            
            # Commit transaction
            conn.commit()
            
            # Close connection
            conn.close()
            
            # Re-initialize the database (recreate default data)
            db.init_db()
            
            return jsonify({
                'success': True,
                'message': 'All data has been deleted successfully. Database has been reset.'
            })
            
        except Exception as e:
            # Rollback on error
            conn.rollback()
            conn.close()
            raise e
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error deleting data: {str(e)}'
        })

@app.route('/admin/delete-specific-data', methods=['POST'])
@login_required
def delete_specific_data():
    """Delete specific types of data"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    try:
        data = request.get_json()
        data_types = data.get('data_types', [])
        
        if not data_types:
            return jsonify({'success': False, 'error': 'No data types selected'})
        
        conn = sqlite3.connect('instance/shop.db')
        cursor = conn.cursor()
        cursor.execute('BEGIN TRANSACTION')
        
        deleted_counts = {}
        
        try:
            # Delete selected data types
            if 'sales' in data_types:
                cursor.execute('DELETE FROM sales')
                deleted_counts['sales'] = cursor.rowcount
            
            if 'expenses' in data_types:
                cursor.execute('DELETE FROM expenses')
                cursor.execute('DELETE FROM expense_categories')
                deleted_counts['expenses'] = cursor.rowcount
            
            if 'products' in data_types:
                # First delete product images from filesystem
                cursor.execute('SELECT image_filename FROM products WHERE image_filename IS NOT NULL')
                images = cursor.fetchall()
                for image in images:
                    if image[0]:
                        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image[0])
                        if os.path.exists(image_path):
                            os.remove(image_path)
                
                cursor.execute('DELETE FROM products')
                deleted_counts['products'] = cursor.rowcount
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'message': f'Selected data deleted successfully.',
                'deleted_counts': deleted_counts
            })
            
        except Exception as e:
            conn.rollback()
            conn.close()
            raise e
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error deleting data: {str(e)}'
        })
# ============ MAIN ============
if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)