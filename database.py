import sqlite3
from datetime import datetime
import threading
import os

class Database:
    _local = threading.local()
    
    def __init__(self, db_path='instance/shop.db'):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute('PRAGMA foreign_keys = ON')
            self._local.connection.execute('PRAGMA busy_timeout = 5000')
        return self._local.connection
    
    def close_connection(self):
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        
        # Users table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Products table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                buying_price REAL NOT NULL,
                selling_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                image_filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sales table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                quantity_sold INTEGER NOT NULL,
                total_price REAL NOT NULL,
                profit REAL NOT NULL,
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        ''')
        
        # ============ NEW TABLES FOR EXPENSES ============
        # Expense Categories table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS expense_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category_type TEXT NOT NULL CHECK(category_type IN ('operating', 'cogs')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Expenses table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                description TEXT,
                expense_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES expense_categories (id)
            )
        ''')
        
        # Create default users
        try:
            cursor = conn.cursor()
            # Admin
            cursor.execute("SELECT id FROM users WHERE username = 'admin'")
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    ('admin', 'admin123', 'admin')
                )
                print("✓ Admin user created: admin / admin123")
            # Employee
            cursor.execute("SELECT id FROM users WHERE username = 'employee'")
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                    ('employee', 'employee123', 'employee')
                )
                print("✓ Employee user created: employee / employee123")
            
            # Create default expense categories
            default_categories = [
                ('Cost of Goods Sold', 'cogs'),
                ('Rent', 'operating'),
                ('Salaries', 'operating'),
                ('Utilities', 'operating'),
                ('Marketing', 'operating'),
                ('Office Supplies', 'operating'),
                ('Insurance', 'operating'),
                ('Maintenance', 'operating'),
                ('Other Operating Expenses', 'operating')
            ]
            
            for name, cat_type in default_categories:
                cursor.execute('''
                    INSERT OR IGNORE INTO expense_categories (name, category_type) 
                    VALUES (?, ?)
                ''', (name, cat_type))
            
            conn.commit()
            print("✓ Expense categories initialized")
        except sqlite3.Error as e:
            print(f"Database init error: {e}")
        finally:
            conn.close()
    
    # ============ USER METHODS ============
    # (No changes to existing user methods)
    def authenticate_user(self, username, password):
        conn = self.get_connection()
        try:
            user = conn.execute(
                'SELECT * FROM users WHERE username = ? AND password = ?',
                (username, password)
            ).fetchone()
            return dict(user) if user else None
        finally:
            pass
    
    def get_user_by_id(self, user_id):
        conn = self.get_connection()
        try:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
            return dict(user) if user else None
        finally:
            pass
    
    def get_user_by_username(self, username):
        conn = self.get_connection()
        try:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            return dict(user) if user else None
        finally:
            pass
    
    def get_all_users(self):
        conn = self.get_connection()
        try:
            users = conn.execute(
                'SELECT id, username, role FROM users ORDER BY role, username'
            ).fetchall()
            return [dict(user) for user in users]
        finally:
            pass
    
    def update_user_password(self, user_id, new_password):
        conn = self.get_connection()
        try:
            conn.execute(
                'UPDATE users SET password = ? WHERE id = ?',
                (new_password, user_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def add_user(self, username, password, role):
        conn = self.get_connection()
        try:
            existing = conn.execute(
                'SELECT id FROM users WHERE username = ?', (username,)
            ).fetchone()
            if existing:
                raise Exception(f"Username '{username}' already exists")
            
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                (username, password, role)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def delete_user(self, user_id):
        conn = self.get_connection()
        try:
            user = conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
            if user and user['role'] == 'admin':
                admins = conn.execute('SELECT COUNT(*) as count FROM users WHERE role = "admin"').fetchone()
                if admins['count'] <= 1:
                    raise Exception("Cannot delete the last admin user")
            
            conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def update_user_role(self, user_id, new_role):
        conn = self.get_connection()
        try:
            if new_role != 'admin':
                current_user = conn.execute('SELECT role FROM users WHERE id = ?', (user_id,)).fetchone()
                if current_user and current_user['role'] == 'admin':
                    admins = conn.execute('SELECT COUNT(*) as count FROM users WHERE role = "admin"').fetchone()
                    if admins['count'] <= 1:
                        raise Exception("Cannot change the last admin to employee")
            
            conn.execute('UPDATE users SET role = ? WHERE id = ?', (new_role, user_id))
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    # ============ PRODUCT METHODS ============
    # (No changes to existing product methods)
    def get_all_products(self):
        conn = self.get_connection()
        try:
            products = conn.execute('SELECT * FROM products ORDER BY name').fetchall()
            return [dict(product) for product in products]
        finally:
            pass
    
    def get_product_by_id(self, product_id):
        conn = self.get_connection()
        try:
            product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
            return dict(product) if product else None
        finally:
            pass
    
    def add_product(self, name, buying_price, selling_price, quantity, image_filename=None):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO products (name, buying_price, selling_price, quantity, image_filename) 
                   VALUES (?, ?, ?, ?, ?)''',
                (name, buying_price, selling_price, quantity, image_filename)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def update_product(self, product_id, name, buying_price, selling_price, quantity, image_filename=None):
        conn = self.get_connection()
        try:
            if image_filename:
                conn.execute('''
                    UPDATE products 
                    SET name = ?, buying_price = ?, selling_price = ?, quantity = ?, image_filename = ?
                    WHERE id = ?
                ''', (name, buying_price, selling_price, quantity, image_filename, product_id))
            else:
                conn.execute('''
                    UPDATE products 
                    SET name = ?, buying_price = ?, selling_price = ?, quantity = ?
                    WHERE id = ?
                ''', (name, buying_price, selling_price, quantity, product_id))
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def delete_product(self, product_id):
        conn = self.get_connection()
        try:
            product = self.get_product_by_id(product_id)
            if product and product.get('image_filename'):
                image_path = os.path.join('static/uploads', product['image_filename'])
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def update_product_quantity(self, product_id, quantity_change):
        conn = self.get_connection()
        try:
            conn.execute(
                'UPDATE products SET quantity = quantity + ? WHERE id = ?',
                (quantity_change, product_id)
            )
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    # ============ SALES METHODS ============
    # (No changes to existing sales methods)
    def record_sale(self, product_id, quantity_sold, total_price, profit):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('BEGIN TRANSACTION')
            
            cursor.execute('''
                INSERT INTO sales (product_id, quantity_sold, total_price, profit, sale_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (product_id, quantity_sold, total_price, profit, datetime.now()))
            
            cursor.execute(
                'UPDATE products SET quantity = quantity - ? WHERE id = ?',
                (quantity_sold, product_id)
            )
            
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def get_all_sales(self):
        conn = self.get_connection()
        try:
            sales = conn.execute('''
                SELECT s.*, p.name as product_name 
                FROM sales s 
                JOIN products p ON s.product_id = p.id 
                ORDER BY s.sale_date DESC
            ''').fetchall()
            return [dict(sale) for sale in sales]
        finally:
            pass
    
    def get_sales_summary(self):
        conn = self.get_connection()
        try:
            summary = conn.execute('''
                SELECT 
                    COUNT(*) as total_sales,
                    COALESCE(SUM(total_price), 0) as total_revenue,
                    COALESCE(SUM(profit), 0) as total_gross_profit
                FROM sales
            ''').fetchone()
            return dict(summary) if summary else {'total_sales': 0, 'total_revenue': 0, 'total_gross_profit': 0}
        finally:
            pass
    
    def get_profit_per_product(self):
        conn = self.get_connection()
        try:
            profit_data = conn.execute('''
                SELECT 
                    p.name as product_name,
                    p.image_filename,
                    COALESCE(SUM(s.quantity_sold), 0) as total_quantity,
                    COALESCE(SUM(s.total_price), 0) as total_revenue,
                    COALESCE(SUM(s.profit), 0) as total_profit
                FROM products p
                LEFT JOIN sales s ON p.id = s.product_id
                GROUP BY p.id, p.name
                ORDER BY total_profit DESC
            ''').fetchall()
            return [dict(data) for data in profit_data]
        finally:
            pass
    
    def get_best_selling_products(self, limit=5):
        conn = self.get_connection()
        try:
            products = conn.execute('''
                SELECT 
                    p.name,
                    p.image_filename,
                    COALESCE(SUM(s.quantity_sold), 0) as total_sold,
                    COALESCE(SUM(s.total_price), 0) as total_revenue
                FROM products p
                LEFT JOIN sales s ON p.id = s.product_id
                GROUP BY p.id, p.name
                ORDER BY total_sold DESC
                LIMIT ?
            ''', (limit,)).fetchall()
            return [dict(product) for product in products]
        finally:
            pass
    
    def get_low_stock_products(self, threshold=10):
        conn = self.get_connection()
        try:
            products = conn.execute('''
                SELECT * FROM products 
                WHERE quantity <= ?
                ORDER BY quantity ASC
            ''', (threshold,)).fetchall()
            return [dict(product) for product in products]
        finally:
            pass
    
    def get_daily_profit_trend(self, days=30):
        conn = self.get_connection()
        try:
            trend = conn.execute('''
                SELECT 
                    DATE(sale_date) as date,
                    COALESCE(SUM(profit), 0) as daily_gross_profit,
                    COALESCE(SUM(total_price), 0) as daily_revenue
                FROM sales
                WHERE sale_date >= DATE('now', ?)
                GROUP BY DATE(sale_date)
                ORDER BY date
            ''', (f'-{days} days',)).fetchall()
            return [dict(row) for row in trend]
        finally:
            pass
    
    # ============ NEW EXPENSE METHODS ============
    
    def add_expense_category(self, name, category_type):
        """Add a new expense category"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO expense_categories (name, category_type) VALUES (?, ?)',
                (name, category_type)
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def get_all_expense_categories(self):
        """Get all expense categories"""
        conn = self.get_connection()
        try:
            categories = conn.execute(
                'SELECT * FROM expense_categories ORDER BY category_type, name'
            ).fetchall()
            return [dict(cat) for cat in categories]
        finally:
            pass
    
    def get_expense_categories_by_type(self, category_type):
        """Get expense categories by type ('operating' or 'cogs')"""
        conn = self.get_connection()
        try:
            categories = conn.execute(
                'SELECT * FROM expense_categories WHERE category_type = ? ORDER BY name',
                (category_type,)
            ).fetchall()
            return [dict(cat) for cat in categories]
        finally:
            pass
    
    def add_expense(self, category_id, amount, description=None):
        """Record a new expense"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO expenses (category_id, amount, description, expense_date) 
                   VALUES (?, ?, ?, ?)''',
                (category_id, amount, description, datetime.now())
            )
            conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def get_all_expenses(self, start_date=None, end_date=None):
        """Get all expenses with optional date range"""
        conn = self.get_connection()
        try:
            query = '''
                SELECT e.*, ec.name as category_name, ec.category_type
                FROM expenses e
                JOIN expense_categories ec ON e.category_id = ec.id
            '''
            params = []
            
            if start_date and end_date:
                query += ' WHERE DATE(e.expense_date) BETWEEN ? AND ?'
                params.extend([start_date, end_date])
            elif start_date:
                query += ' WHERE DATE(e.expense_date) >= ?'
                params.append(start_date)
            elif end_date:
                query += ' WHERE DATE(e.expense_date) <= ?'
                params.append(end_date)
            
            query += ' ORDER BY e.expense_date DESC'
            expenses = conn.execute(query, params).fetchall()
            return [dict(exp) for exp in expenses]
        finally:
            pass
    
    def get_expense_summary(self, start_date=None, end_date=None):
        """Get expense summary by category type"""
        conn = self.get_connection()
        try:
            query = '''
                SELECT 
                    ec.category_type,
                    COALESCE(SUM(e.amount), 0) as total_amount
                FROM expense_categories ec
                LEFT JOIN expenses e ON ec.id = e.category_id
            '''
            params = []
            
            if start_date and end_date:
                query += ' WHERE DATE(e.expense_date) BETWEEN ? AND ?'
                params.extend([start_date, end_date])
            elif start_date:
                query += ' WHERE DATE(e.expense_date) >= ?'
                params.append(start_date)
            elif end_date:
                query += ' WHERE DATE(e.expense_date) <= ?'
                params.append(end_date)
            
            query += ' GROUP BY ec.category_type'
            summary = conn.execute(query, params).fetchall()
            return {row['category_type']: row['total_amount'] for row in summary}
        finally:
            pass
    
    def get_expenses_by_category(self, start_date=None, end_date=None):
        """Get expenses grouped by category"""
        conn = self.get_connection()
        try:
            query = '''
                SELECT 
                    ec.id,
                    ec.name as category_name,
                    ec.category_type,
                    COALESCE(SUM(e.amount), 0) as total_amount,
                    COUNT(e.id) as expense_count
                FROM expense_categories ec
                LEFT JOIN expenses e ON ec.id = e.category_id
            '''
            params = []
            
            if start_date and end_date:
                query += ' WHERE DATE(e.expense_date) BETWEEN ? AND ?'
                params.extend([start_date, end_date])
            elif start_date:
                query += ' WHERE DATE(e.expense_date) >= ?'
                params.append(start_date)
            elif end_date:
                query += ' WHERE DATE(e.expense_date) <= ?'
                params.append(end_date)
            
            query += ' GROUP BY ec.id, ec.name ORDER BY total_amount DESC'
            expenses = conn.execute(query, params).fetchall()
            return [dict(exp) for exp in expenses]
        finally:
            pass
    
    def get_total_expenses(self, start_date=None, end_date=None):
        """Get total expenses"""
        conn = self.get_connection()
        try:
            query = 'SELECT COALESCE(SUM(amount), 0) as total FROM expenses'
            params = []
            
            if start_date and end_date:
                query += ' WHERE DATE(expense_date) BETWEEN ? AND ?'
                params.extend([start_date, end_date])
            elif start_date:
                query += ' WHERE DATE(expense_date) >= ?'
                params.append(start_date)
            elif end_date:
                query += ' WHERE DATE(expense_date) <= ?'
                params.append(end_date)
            
            result = conn.execute(query, params).fetchone()
            return result['total'] if result else 0
        finally:
            pass
    
    def delete_expense(self, expense_id):
        """Delete an expense"""
        conn = self.get_connection()
        try:
            conn.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
            conn.commit()
            return True
        except sqlite3.Error as e:
            conn.rollback()
            raise e
        finally:
            pass
    
    def get_profit_analysis(self, start_date=None, end_date=None):
        """Get complete profit analysis (Gross Profit and Net Profit)"""
        conn = self.get_connection()
        try:
            # Get revenue and gross profit from sales
            sales_query = '''
                SELECT 
                    COALESCE(SUM(total_price), 0) as total_revenue,
                    COALESCE(SUM(profit), 0) as total_gross_profit
                FROM sales
            '''
            sales_params = []
            
            if start_date and end_date:
                sales_query += ' WHERE DATE(sale_date) BETWEEN ? AND ?'
                sales_params.extend([start_date, end_date])
            elif start_date:
                sales_query += ' WHERE DATE(sale_date) >= ?'
                sales_params.append(start_date)
            elif end_date:
                sales_query += ' WHERE DATE(sale_date) <= ?'
                sales_params.append(end_date)
            
            sales_result = conn.execute(sales_query, sales_params).fetchone()
            
            # Get expenses
            expense_summary = self.get_expense_summary(start_date, end_date)
            
            total_revenue = sales_result['total_revenue'] if sales_result else 0
            total_gross_profit = sales_result['total_gross_profit'] if sales_result else 0
            
            total_cogs = expense_summary.get('cogs', 0)
            total_operating_expenses = expense_summary.get('operating', 0)
            total_expenses = total_cogs + total_operating_expenses
            
            # Calculate net profit
            # Gross Profit = Revenue - COGS (from sales profit calculation)
            # Net Profit = Gross Profit - Operating Expenses
            net_profit = total_gross_profit - total_operating_expenses
            
            return {
                'total_revenue': total_revenue,
                'total_gross_profit': total_gross_profit,
                'total_cogs': total_cogs,
                'total_operating_expenses': total_operating_expenses,
                'total_expenses': total_expenses,
                'net_profit': net_profit,
                'gross_profit_margin': (total_gross_profit / total_revenue * 100) if total_revenue > 0 else 0,
                'net_profit_margin': (net_profit / total_revenue * 100) if total_revenue > 0 else 0
            }
        finally:
            pass
    
    def __del__(self):
        self.close_connection()