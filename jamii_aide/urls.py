from django.urls import path
from django.urls import path

from jamii_aide.views import (
    AdminDashboardView,
    LoginPageView,
    NurseDashboardView,
    OrganizationAdminDashboardView,
    RoleRedirectView,
    SignupView,
    UserDashboardView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup-page'),
    path('login/', LoginPageView.as_view(), name='login-page'),
    path('dashboard/', RoleRedirectView.as_view(), name='dashboard'),
    path('dashboard/user', UserDashboardView.as_view(), name='dashboard-user'),
    path('dashboard/nurse', NurseDashboardView.as_view(), name='dashboard-nurse'),
    path('dashboard/admin', AdminDashboardView.as_view(), name='dashboard-admin'),
    path('dashboard/organization-admin', OrganizationAdminDashboardView.as_view(), name='dashboard-organization-admin'),
]
