import { Routes } from '@angular/router';
import { Access } from './access';
import { Login } from './login';
import { Error } from './error';
import { Register } from './register';
import { guestOnlyGuard } from '../../core/auth/guest-only.guard';

export default [
    { path: 'access', component: Access },
    { path: 'error', component: Error },
    { path: 'login', component: Login, canActivate: [guestOnlyGuard] },
    { path: 'register', component: Register, canActivate: [guestOnlyGuard] }
] as Routes;
