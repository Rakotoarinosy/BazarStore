import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';

export const adminGuard: CanActivateFn = () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    if (auth.currentUser()?.role === 'admin') return true;

    return auth
        .refresh()
        .pipe(
            map(() => auth.currentUser()?.role === 'admin' ? true : router.createUrlTree(['/auth/access'])),
            catchError(() => of(router.createUrlTree(['/auth/login'])))
        );
};
