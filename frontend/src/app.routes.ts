import { Routes } from '@angular/router';
import { AppLayout } from './app/layout/component/app.layout';
import { Dashboard } from './app/pages/dashboard/dashboard';
import { Documentation } from './app/pages/documentation/documentation';
import { Landing } from './app/pages/landing/landing';
import { Notfound } from './app/pages/notfound/notfound';
import { Users } from './app/pages/users/users';
import { Categories } from './app/pages/categories/categories';
import { adminGuard } from './app/core/auth/admin.guard';

export const appRoutes: Routes = [
    {
        path: '',
        component: Landing,
        pathMatch: 'full'
    },
    {
        path: 'backoffice',
        component: AppLayout,
        children: [
            { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
            { path: 'dashboard', component: Dashboard },
            { path: 'users', component: Users, canActivate: [adminGuard] },
            { path: 'categories', component: Categories, canActivate: [adminGuard] },
            { path: 'uikit', loadChildren: () => import('./app/pages/uikit/uikit.routes') },
            { path: 'documentation', component: Documentation },
            { path: 'pages', loadChildren: () => import('./app/pages/pages.routes') }
        ]
    },
    { path: 'landing', component: Landing },
    { path: 'dashboard', redirectTo: '/backoffice/dashboard' },
    { path: 'uikit/:page', redirectTo: '/backoffice/uikit/:page' },
    { path: 'uikit', redirectTo: '/backoffice/uikit' },
    { path: 'pages/:page', redirectTo: '/backoffice/pages/:page' },
    { path: 'documentation', redirectTo: '/backoffice/documentation' },
    { path: 'pages', redirectTo: '/backoffice/pages' },
    { path: 'notfound', component: Notfound },
    { path: 'auth', loadChildren: () => import('./app/pages/auth/auth.routes') },
    { path: '**', redirectTo: '/notfound' }
];
