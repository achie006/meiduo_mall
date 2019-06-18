from django.contrib.auth import mixins
from django.views import View


class LoginRequiredView(mixins.LoginRequiredMixin, View):
    pass