# app.py - سوق الأدوات المضمونة (الإصدار النهائي المتكامل)
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import secrets
import json

# ===== إعداد التطبيق =====
app = Flask(__name__)
app.secret_key = 'SUPER_SECRET_KEY_2026_CHANGE_ME'

# ===== قاعدة البيانات =====
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///marketplace.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ===== إعدادات الملفات =====
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# ===== إعدادات المنصة =====
app.config['COMMISSION_RATE'] = 0.25  # 25% عمولة
app.config['PLATFORM_WALLET'] = '0x74DAeAd234A3BF24f38ac4ef65999Bb6bAAA5FaF'  # محفظة المنصة (Trust Wallet)
app.config['TRUST_WALLET_ADDRESS'] = '0x74DAeAd234A3BF24f38ac4ef65999Bb6bAAA5FaF'  # عنوان Trust Wallet

# ===== تهيئة قاعدة البيانات =====
db = SQLAlchemy(app)

# ===== نظام تسجيل الدخول =====
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول أولاً'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===============================
# ===== نماذج قاعدة البيانات =====
# ===============================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='buyer')
    
    # بيانات إضافية
    full_name = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    trust_wallet_address = db.Column(db.String(100), nullable=True)  # عنوان Trust Wallet للبائع
    
    # إحصائيات البائع
    total_sales = db.Column(db.Integer, default=0)
    total_earnings = db.Column(db.Float, default=0.0)
    rating = db.Column(db.Float, default=0.0)
    rating_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Tool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), default='other')
    file_path = db.Column(db.String(200), nullable=True)
    file_hash = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(20), default='listed')
    views = db.Column(db.Integer, default=0)
    downloads = db.Column(db.Integer, default=0)
    sales_count = db.Column(db.Integer, default=0)
    
    # كوبونات الخصم
    discount_percent = db.Column(db.Float, default=0.0)
    discount_expiry = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    seller = db.relationship('User', backref='tools')
    reviews = db.relationship('Review', backref='tool', lazy=True)
    
    @property
    def final_price(self):
        if self.discount_percent > 0 and self.discount_expiry and self.discount_expiry > datetime.utcnow():
            return self.price * (1 - self.discount_percent / 100)
        return self.price
    
    @property
    def is_on_sale(self):
        return self.discount_percent > 0 and self.discount_expiry and self.discount_expiry > datetime.utcnow()

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    amount = db.Column(db.Float, nullable=False)
    commission = db.Column(db.Float, nullable=False)
    seller_share = db.Column(db.Float, nullable=False)
    
    platform_wallet = db.Column(db.String(100), nullable=True)
    seller_wallet = db.Column(db.String(100), nullable=True)
    
    status = db.Column(db.String(20), default='pending')  # pending, completed, refunded, escrow
    is_escrow = db.Column(db.Boolean, default=True)  # نظام وساطة مفعل افتراضياً
    
    escrow_released = db.Column(db.Boolean, default=False)
    escrow_release_date = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    tool = db.relationship('Tool')
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    seller = db.relationship('User', foreign_keys=[seller_id])
    review = db.relationship('Review', backref='transaction', uselist=False)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=False)
    
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    seller = db.relationship('User', foreign_keys=[seller_id])

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='notifications')

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_percent = db.Column(db.Float, nullable=False)
    tool_id = db.Column(db.Integer, db.ForeignKey('tool.id'), nullable=True)
    max_uses = db.Column(db.Integer, default=1)
    used_count = db.Column(db.Integer, default=0)
    expiry_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tool = db.relationship('Tool', backref='coupons')

# ===== إنشاء الجداول =====
with app.app_context():
    db.create_all()
    print("✅ قاعدة البيانات جاهزة!")

# ===============================
# ===== دوال مساعدة =====
# ===============================

def create_notification(user_id, title, message, type='info', link=None):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=type,
        link=link
    )
    db.session.add(notification)
    db.session.commit()
    return notification

def calculate_seller_rating(seller_id):
    reviews = Review.query.filter_by(seller_id=seller_id).all()
    if not reviews:
        return 0.0
    avg = sum(r.rating for r in reviews) / len(reviews)
    return round(avg, 1)

# ===============================
# ===== الصفحات الرئيسية =====
# ===============================

@app.route('/')
def index():
    category = request.args.get('category', '')
    sort = request.args.get('sort', 'newest')
    search = request.args.get('search', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    
    query = Tool.query.filter_by(status='listed')
    
    if search:
        query = query.filter(
            (Tool.name.contains(search)) | 
            (Tool.description.contains(search))
        )
    
    if category and category != 'all':
        query = query.filter_by(category=category)
    
    if min_price is not None:
        query = query.filter(Tool.price >= min_price)
    if max_price is not None:
        query = query.filter(Tool.price <= max_price)
    
    if sort == 'newest':
        query = query.order_by(Tool.created_at.desc())
    elif sort == 'price_low':
        query = query.order_by(Tool.price.asc())
    elif sort == 'price_high':
        query = query.order_by(Tool.price.desc())
    elif sort == 'popular':
        query = query.order_by(Tool.sales_count.desc())
    
    tools = query.all()
    categories = db.session.query(Tool.category).distinct().all()
    categories = [c[0] for c in categories if c[0] != 'other']
    
    return render_template('index.html', 
                          tools=tools, 
                          categories=categories,
                          category=category,
                          sort=sort,
                          search=search,
                          min_price=min_price,
                          max_price=max_price)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'buyer')
        
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'error')
            return render_template('login.html')
        
        if user.role != role:
            flash(f'هذا الحساب ليس {role}', 'error')
            return render_template('login.html')
        
        login_user(user)
        flash(f'مرحباً {user.username}!', 'success')
        
        if user.role == 'seller':
            return redirect(url_for('seller_dashboard'))
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('تم تسجيل الخروج', 'success')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'buyer')
        
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('البريد الإلكتروني مستخدم', 'error')
            return render_template('register.html')
        
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash(f'تم التسجيل كـ {role}', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/profile', methods=['GET'])
@login_required
def profile():
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).all()
    return render_template('profile.html', user=current_user, notifications=notifications)

@app.route('/profile/update', methods=['POST'])
@login_required
def profile_update():
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    trust_wallet_address = request.form.get('trust_wallet_address', '').strip()
    
    current_user.full_name = full_name
    current_user.phone = phone
    current_user.trust_wallet_address = trust_wallet_address
    
    db.session.commit()
    flash('تم تحديث الملف الشخصي', 'success')
    return redirect(url_for('profile'))

@app.route('/notifications/mark-read/<int:notif_id>')
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
    return redirect(request.referrer or url_for('profile'))

# ===============================
# ===== البائع =====
# ===============================

@app.route('/seller/dashboard')
@login_required
def seller_dashboard():
    if current_user.role != 'seller':
        flash('هذه الصفحة للبائعين فقط', 'error')
        return redirect(url_for('index'))
    
    tools = Tool.query.filter_by(seller_id=current_user.id).all()
    transactions = Transaction.query.filter_by(seller_id=current_user.id).all()
    reviews = Review.query.filter_by(seller_id=current_user.id).all()
    
    total_earnings = sum(t.seller_share for t in transactions)
    total_sales = len(transactions)
    total_commission = sum(t.commission for t in transactions)
    avg_rating = calculate_seller_rating(current_user.id)
    
    total_views = sum(t.views for t in tools)
    total_downloads = sum(t.downloads for t in tools)
    
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    monthly_sales = len([t for t in transactions if t.created_at >= month_start])
    monthly_earnings = sum(t.seller_share for t in transactions if t.created_at >= month_start)
    
    return render_template('seller_dashboard.html',
                           tools=tools,
                           total_earnings=total_earnings,
                           total_sales=total_sales,
                           total_commission=total_commission,
                           avg_rating=avg_rating,
                           total_views=total_views,
                           total_downloads=total_downloads,
                           monthly_sales=monthly_sales,
                           monthly_earnings=monthly_earnings)

@app.route('/seller/add-tool', methods=['GET', 'POST'])
@login_required
def add_tool():
    if current_user.role != 'seller':
        flash('هذه الصفحة للبائعين فقط', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = float(request.form.get('price'))
        category = request.form.get('category', 'other')
        
        file = request.files.get('file')
        file_path = None
        if file and file.filename:
            filename = secure_filename(file.filename)
            os.makedirs('uploads', exist_ok=True)
            file_path = os.path.join('uploads', filename)
            file.save(file_path)
        
        tool = Tool(
            seller_id=current_user.id,
            name=name,
            description=description,
            price=price,
            category=category,
            file_path=file_path,
            status='listed'
        )
        db.session.add(tool)
        db.session.commit()
        
        flash('تم إضافة الأداة', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('add_tool.html')

@app.route('/seller/edit-tool/<int:tool_id>', methods=['GET', 'POST'])
@login_required
def edit_tool(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    if tool.seller_id != current_user.id:
        flash('هذه الأداة ليست ملكك', 'error')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        tool.name = request.form.get('name')
        tool.description = request.form.get('description')
        tool.price = float(request.form.get('price'))
        tool.category = request.form.get('category', 'other')
        
        discount = float(request.form.get('discount', 0))
        discount_days = int(request.form.get('discount_days', 0))
        if discount > 0 and discount_days > 0:
            tool.discount_percent = discount
            tool.discount_expiry = datetime.utcnow() + timedelta(days=discount_days)
        else:
            tool.discount_percent = 0
            tool.discount_expiry = None
        
        db.session.commit()
        flash('تم تحديث الأداة', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('edit_tool.html', tool=tool)

@app.route('/seller/delete-tool/<int:tool_id>', methods=['POST'])
@login_required
def delete_tool(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    if tool.seller_id != current_user.id:
        flash('هذه الأداة ليست ملكك', 'error')
        return redirect(url_for('seller_dashboard'))
    
    if tool.file_path and os.path.exists(tool.file_path):
        os.remove(tool.file_path)
    
    db.session.delete(tool)
    db.session.commit()
    flash('تم حذف الأداة', 'success')
    return redirect(url_for('seller_dashboard'))

# ===============================
# ===== المشتري =====
# ===============================

@app.route('/tool/<int:tool_id>')
def tool_detail(tool_id):
    tool = Tool.query.get_or_404(tool_id)
    tool.views += 1
    db.session.commit()
    
    reviews = Review.query.filter_by(tool_id=tool_id).order_by(Review.created_at.desc()).all()
    avg_rating = sum(r.rating for r in reviews) / len(reviews) if reviews else 0
    
    return render_template('tool_detail.html', tool=tool, reviews=reviews, avg_rating=avg_rating)

@app.route('/buy/<int:tool_id>')
@login_required
def buy_tool(tool_id):
    if current_user.role != 'buyer':
        flash('المشتري فقط يمكنه الشراء', 'error')
        return redirect(url_for('index'))
    
    tool = Tool.query.get_or_404(tool_id)
    if tool.status != 'listed':
        flash('هذه الأداة غير متاحة', 'error')
        return redirect(url_for('index'))
    
    seller = User.query.get(tool.seller_id)
    final_price = tool.final_price
    
    commission = final_price * app.config['COMMISSION_RATE']
    seller_share = final_price - commission
    
    transaction = Transaction(
        tool_id=tool.id,
        buyer_id=current_user.id,
        seller_id=seller.id,
        amount=final_price,
        commission=commission,
        seller_share=seller_share,
        platform_wallet=app.config['PLATFORM_WALLET'],
        seller_wallet=seller.trust_wallet_address or 'لم يتم إضافة عنوان',
        status='escrow',
        is_escrow=True,
        escrow_released=False
    )
    db.session.add(transaction)
    
    tool.status = 'sold'
    tool.sales_count += 1
    seller.total_sales += 1
    seller.total_earnings += seller_share
    
    db.session.commit()
    
    create_notification(
        user_id=seller.id,
        title='🛒 تم شراء منتجك!',
        message=f'قام {current_user.username} بشراء "{tool.name}" مقابل ${"%.2f"|format(final_price)}',
        type='sale',
        link=f'/tool/{tool.id}'
    )
    
    flash(f'''
    ✅ تم شراء الأداة!
    💰 المبلغ: ${"%.2f"|format(final_price)}
    🏢 عمولة المنصة (25%): ${"%.2f"|format(commission)}
    👤 حصة البائع (75%): ${"%.2f"|format(seller_share)}
    🔑 عنوان البائع: {seller.trust_wallet_address or 'لم يضف عنواناً'}
    ⏳ الأموال محتجزة في نظام الوساطة حتى تأكيد الاستلام
    ''', 'success')
    
    return redirect(url_for('index'))

@app.route('/review/<int:transaction_id>', methods=['GET', 'POST'])
@login_required
def add_review(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    
    if transaction.buyer_id != current_user.id:
        flash('أنت لست مشتري هذه الأداة', 'error')
        return redirect(url_for('index'))
    
    if transaction.review:
        flash('لقد قمت بتقييم هذه الأداة بالفعل', 'warning')
        return redirect(url_for('tool_detail', tool_id=transaction.tool_id))
    
    if request.method == 'POST':
        rating = int(request.form.get('rating', 5))
        comment = request.form.get('comment', '').strip()
        
        if rating < 1 or rating > 5:
            flash('التقييم يجب أن يكون بين 1 و 5', 'error')
            return render_template('add_review.html', transaction=transaction)
        
        review = Review(
            tool_id=transaction.tool_id,
            buyer_id=current_user.id,
            seller_id=transaction.seller_id,
            transaction_id=transaction.id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)
        
        seller = User.query.get(transaction.seller_id)
        seller.rating = calculate_seller_rating(seller.id)
        
        db.session.commit()
        
        create_notification(
            user_id=seller.id,
            title='⭐ تقييم جديد',
            message=f'قام {current_user.username} بتقييم منتجك بـ {rating} نجوم',
            type='info',
            link=f'/tool/{transaction.tool_id}'
        )
        
        flash('تم إضافة التقييم بنجاح!', 'success')
        return redirect(url_for('tool_detail', tool_id=transaction.tool_id))
    
    return render_template('add_review.html', transaction=transaction)

@app.route('/seller/<int:seller_id>')
def public_seller_page(seller_id):
    seller = User.query.get_or_404(seller_id)
    if seller.role != 'seller':
        flash('هذا المستخدم ليس بائعاً', 'error')
        return redirect(url_for('index'))
    
    tools = Tool.query.filter_by(seller_id=seller_id, status='listed').all()
    reviews = Review.query.filter_by(seller_id=seller_id).order_by(Review.created_at.desc()).all()
    avg_rating = calculate_seller_rating(seller_id)
    
    return render_template('public_seller.html',
                           seller=seller,
                           tools=tools,
                           reviews=reviews,
                           avg_rating=avg_rating)

# ===== تشغيل التطبيق =====
if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    print("🚀 تشغيل سوق الأدوات الرقمية (الإصدار النهائي)...")
    print("🌐 افتح: http://127.0.0.1:7331")
    print("📱 للوصول من الأجهزة الأخرى: http://[IP]:7331")
    app.run(debug=True, host='0.0.0.0', port=7331)
