# Jamii Aide Django Backend

A production-ready Django + Django REST Framework backend for Jamii Aide healthcare coordination platform.

## 🎯 Features

✅ **User Authentication** - JWT-based with role-based access control  
✅ **Family Member Management** - Add and manage family members back home  
✅ **Healthcare Nurse Profiles** - Complete nurse management system  
✅ **Appointment System** - Full lifecycle booking and management  
✅ **Health Records** - Store vital signs, notes, diagnoses  
✅ **Payment Processing** - M-Pesa, Stripe, and PesaPal integration ready  
✅ **Reviews & Ratings** - Quality assurance system  
✅ **Admin Dashboard** - Django admin for management  
✅ **API Documentation** - Auto-generated with DRF  

## 🛠️ Tech Stack

- **Framework**: Django 4.2
- **API**: Django REST Framework
- **Database**: PostgreSQL
- **Authentication**: JWT (Simple JWT)
- **Admin**: Django Admin
- **Testing**: Pytest + Pytest-Django
- **Production**: Gunicorn + Whitenoise

## 📋 Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Git

## 🚀 Installation & Setup

### Step 1: Clone & Setup Virtual Environment

```bash
# Create project directory
mkdir jamii-aide-backend
cd jamii-aide-backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip
```

### Step 2: Install Dependencies

```bash
pip install -r requirements_django.txt
```

### Step 3: Create Django Project Structure

```bash
# Create Django project (if not already done)
django-admin startproject config .
django-admin startapp jamii_aide
```

### Step 4: Configure Environment

```bash
# Copy environment template
cp .env_django.example .env

# Edit .env with your settings
nano .env
```

Key settings to configure:

```env
SECRET_KEY=your-secret-key-here
DEBUG=False  # Set to False in production
DB_NAME=jamii_aide_db
DB_USER=postgres
DB_PASSWORD=your_password
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### Step 5: Database Setup

```bash
# Create PostgreSQL database
createdb jamii_aide_db

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
# Email: admin@example.com
# Password: secure_password
```

### Step 6: Copy Files to Project

Copy the following files to your Django project:

- `django_models.py` → `jamii_aide/models.py`
- `django_serializers.py` → `jamii_aide/serializers.py`
- `django_views.py` → `jamii_aide/views.py`
- `urls.py` → `config/urls.py`
- `settings.py` → `config/settings.py`

### Step 7: Run Development Server

```bash
python manage.py runserver

# Server runs on http://localhost:8000
```

## 📚 API Documentation

Once running, access:

- **Swagger UI**: `http://localhost:8000/api/schema/swagger/`
- **ReDoc**: `http://localhost:8000/api/schema/redoc/`
- **Admin Panel**: `http://localhost:8000/admin/`

## 🔑 API Endpoints

### Authentication

```
POST   /api/auth/register/         # Register new user
POST   /api/auth/login/            # Login
POST   /api/auth/refresh/          # Refresh token
GET    /api/auth/me/               # Get current user
```

### Family Members

```
GET    /api/family-members/        # List family members
POST   /api/family-members/        # Create family member
GET    /api/family-members/{id}/   # Get details
PUT    /api/family-members/{id}/   # Update
DELETE /api/family-members/{id}/   # Delete
```

### Healthcare Nurses

```
GET    /api/nurses/                # List nurses
GET    /api/nurses/{id}/           # Get nurse profile
GET    /api/nurses/{id}/stats/     # Get statistics
GET    /api/nurses/{id}/availability/  # Get availability
POST   /api/nurses/{id}/availability/  # Add availability
PUT    /api/nurses/{id}/           # Update profile
```

### Appointments

```
GET    /api/appointments/          # List appointments
POST   /api/appointments/          # Create appointment
GET    /api/appointments/{id}/     # Get details
PUT    /api/appointments/{id}/     # Update
POST   /api/appointments/{id}/confirm/  # Confirm (nurse)
POST   /api/appointments/{id}/complete/ # Complete (nurse)
POST   /api/appointments/{id}/cancel/   # Cancel
```

### Health Records

```
GET    /api/health-records/        # List records
POST   /api/health-records/        # Create record
GET    /api/health-records/{id}/   # Get details
PUT    /api/health-records/{id}/   # Update
DELETE /api/health-records/{id}/   # Delete
```

### Prescriptions

```
GET    /api/prescriptions/         # List prescriptions
POST   /api/prescriptions/         # Create prescription
GET    /api/prescriptions/{id}/    # Get details
PUT    /api/prescriptions/{id}/    # Update
POST   /api/prescriptions/{id}/refill/  # Request refill
```

### Payments

```
GET    /api/payments/              # List payments
POST   /api/payments/              # Initiate payment
GET    /api/payments/{id}/         # Get details
POST   /api/payments/mpesa-callback/    # M-Pesa callback
POST   /api/payments/stripe-webhook/    # Stripe webhook
POST   /api/payments/pesapal-ipn/       # PesaPal IPN
POST   /api/payments/{id}/refund/  # Refund payment
GET    /api/payments/stats/        # Get statistics
```

### Reviews

```
GET    /api/reviews/               # List reviews
POST   /api/reviews/               # Create review
GET    /api/reviews/{id}/          # Get details
PUT    /api/reviews/{id}/          # Update
DELETE /api/reviews/{id}/          # Delete
GET    /api/reviews/nurse/{id}/stats/   # Nurse statistics
```

## 🔐 Authentication

### Login Flow

1. **Register**

   ```bash
   POST /api/auth/register/
   {
     "email": "user@example.com",
     "password": "SecurePass123!",
     "first_name": "John",
     "last_name": "Doe",
     "role": "DIASPORA_USER"
   }
   ```

2. **Login**

   ```bash
   POST /api/auth/login/
   {
     "email": "user@example.com",
     "password": "SecurePass123!"
   }
   ```

3. **Use Token**

   ```bash
   GET /api/family-members/
   Headers: Authorization: Bearer <access_token>
   ```

4. **Refresh Token**

   ```bash
   POST /api/auth/refresh/
   {
     "refresh": "<refresh_token>"
   }
   ```

## 📁 Project Structure

```
jamii-aide-backend/
├── config/
│   ├── settings.py          # Django settings
│   ├── urls.py             # URL routing
│   ├── wsgi.py            # WSGI config
│   └── asgi.py            # ASGI config (for async)
├── jamii_aide/
│   ├── models.py          # Database models
│   ├── serializers.py     # DRF serializers
│   ├── views.py           # API views
│   ├── urls.py            # App URLs
│   ├── admin.py           # Admin config
│   ├── tests.py           # Tests
│   └── apps.py            # App config
├── manage.py              # Django CLI
├── requirements_django.txt # Dependencies
├── .env.example          # Environment template
└── README.md             # This file
```

## 🧪 Testing

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=jamii_aide

# Run specific test
pytest jamii_aide/tests/test_appointments.py
```

### Create Test Data

```bash
python manage.py shell
from jamii_aide.models import CustomUser, HealthcareNurse
# Create test users and data
```

## 📦 Deployment

### Using Gunicorn

```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Using Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11

WORKDIR /app

COPY requirements_django.txt .
RUN pip install -r requirements_django.txt

COPY . .

RUN python manage.py collectstatic --noinput

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

Build and run:

```bash
docker build -t jamii-aide-backend .
docker run -p 8000:8000 --env-file .env jamii-aide-backend
```

### On Heroku

```bash
# Install Heroku CLI
heroku login

# Create app
heroku create jamii-aide-backend

# Set environment variables
heroku config:set SECRET_KEY=your_secret_key

# Deploy
git push heroku main

# Run migrations
heroku run python manage.py migrate
```

## 🔧 Management Commands

```bash
# Create superuser
python manage.py createsuperuser

# Run migrations
python manage.py migrate

# Make migrations
python manage.py makemigrations

# Collect static files
python manage.py collectstatic

# Create cache table
python manage.py createcachetable

# Django shell
python manage.py shell

# Run tests
python manage.py test
```

## 📊 Admin Interface

Access Django admin at `http://localhost:8000/admin/`

Manage:

- Users & Roles
- Family Members
- Healthcare Nurses
- Appointments
- Health Records
- Payments
- Reviews

## 🔌 Connecting Frontend

### Frontend Configuration

In your React `.env.local`:

```env
REACT_APP_API_URL=http://localhost:8000/api
REACT_APP_JWT_EXPIRY=30
```

### API Client Setup

```typescript
import axios from 'axios';

const API = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
});

API.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default API;
```

### Making Requests

```typescript
// Register
await API.post('/auth/register/', {
  email, password, first_name, last_name, role
});

// Login
const response = await API.post('/auth/login/', { email, password });
localStorage.setItem('access_token', response.data.access_token);

// Get appointments
const appointments = await API.get('/appointments/');

// Book appointment
await API.post('/appointments/', appointmentData);
```

## 🐛 Troubleshooting

### Database Connection Error

```bash
# Check PostgreSQL is running
psql -U postgres -d jamii_aide_db

# If database doesn't exist
createdb jamii_aide_db

# Run migrations
python manage.py migrate
```

### Static Files Not Loading

```bash
# Collect static files
python manage.py collectstatic --noinput

# In production, use WhiteNoise middleware (included in settings)
```

### CORS Errors

Update `.env`:

```env
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### Token Expired

Generate new token using refresh token:

```bash
POST /api/auth/refresh/
{
  "refresh": "<refresh_token>"
}
```

## 📈 Performance Tips

1. **Use select_related() and prefetch_related()**

   ```python
   queryset = Appointment.objects.select_related('nurse', 'family_member')
   ```

2. **Add database indexes** (already in models)

3. **Enable caching**

   ```python
   from django.views.decorators.cache import cache_page
   
   @cache_page(60 * 15)  # 15 minutes
   def my_view(request):
       ...
   ```

4. **Use pagination** (configured in settings)

5. **Enable compression**

   ```python
   MIDDLEWARE = [
       'django.middleware.gzip.GZipMiddleware',
       ...
   ]
   ```

## 🚀 Next Steps

1. ✅ Database setup
2. ✅ Run migrations
3. ✅ Create superuser
4. ✅ Start server
5. ✅ Test API endpoints
6. ✅ Connect React frontend
7. ✅ Implement M-Pesa integration
8. ✅ Add email notifications
9. ✅ Configure Celery for async tasks
10. ⏳ Deploy to production

## 📞 Support

- **API Docs**: `http://localhost:8000/api/schema/swagger/`
- **Admin Panel**: `http://localhost:8000/admin/`
- **Django Docs**: `https://docs.djangoproject.com/`
- **DRF Docs**: `https://www.django-rest-framework.org/`

## 📝 License

[Your License Here]

---

Your Django backend is ready! Start building! 