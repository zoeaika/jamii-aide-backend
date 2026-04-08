from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm

from jamii_aide.models import CustomUser, UserRole


class SignupForm(UserCreationForm):
    email = forms.EmailField(max_length=254)

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = UserRole.USER
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

    error_messages = {
        "invalid_login": "Please enter a valid username and password.",
        "inactive": "This account is inactive.",
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        password = cleaned_data.get("password")

        if username and password:
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
            )
            if self.user_cache is None:
                raise forms.ValidationError(self.error_messages["invalid_login"])
            if not self.user_cache.is_active:
                raise forms.ValidationError(self.error_messages["inactive"])

        return cleaned_data

    def get_user(self):
        return self.user_cache
