import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from './auth.service';

const API_PREFIX = '/api/v1/';
const AUTH_ENDPOINTS_WITHOUT_REFRESH = ['/auth/login', '/auth/register', '/auth/google', '/auth/refresh'];

export const authInterceptor: HttpInterceptorFn = (request, next) => {
    if (!request.url.startsWith(API_PREFIX)) {
        return next(request);
    }

    const auth = inject(AuthService);
    const token = auth.accessToken();
    const authorizedRequest = request.clone({
        withCredentials: true,
        ...(token ? { setHeaders: { Authorization: `Bearer ${token}` } } : {})
    });
    const isAuthSetupRequest = AUTH_ENDPOINTS_WITHOUT_REFRESH.some((path) => request.url.includes(path));

    return next(authorizedRequest).pipe(
        catchError((error: unknown) => {
            if (!(error instanceof HttpErrorResponse) || error.status !== 401 || isAuthSetupRequest) {
                return throwError(() => error);
            }

            return auth.refresh().pipe(
                switchMap((refreshedToken) =>
                    next(
                        request.clone({
                            withCredentials: true,
                            setHeaders: { Authorization: `Bearer ${refreshedToken}` }
                        })
                    )
                ),
                catchError(() => {
                    auth.clearSession();
                    return throwError(() => error);
                })
            );
        })
    );
};
