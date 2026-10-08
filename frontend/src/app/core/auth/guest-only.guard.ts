import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';

function homeForRole(role: string | undefined, router: Router) {
    return ['admin', 'commercial', 'manager'].includes(role ?? '')
        ? router.createUrlTree(['/backoffice/dashboard'])
        : router.createUrlTree(['/']);
}

export const guestOnlyGuard: CanActivateFn = () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    if (auth.currentUser()) {
        return homeForRole(auth.currentUser()?.role, router);
    }

    return auth.refresh().pipe(
        map(() => homeForRole(auth.currentUser()?.role, router)),
        catchError(() => of(true))
    );
};
