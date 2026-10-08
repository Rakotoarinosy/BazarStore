import { Component, inject } from '@angular/core';
import { MenuItem } from 'primeng/api';
import { Router, RouterModule } from '@angular/router';
import { CommonModule } from '@angular/common';
import { StyleClassModule } from 'primeng/styleclass';
import { AppConfigurator } from './app.configurator';
import { LayoutService } from '@/app/layout/service/layout.service';
import { EMPTY, catchError, finalize } from 'rxjs';
import { AuthService } from '@/app/core/auth/auth.service';

@Component({
    selector: 'app-topbar',
    standalone: true,
    imports: [RouterModule, CommonModule, StyleClassModule, AppConfigurator],
    templateUrl: './app.topbar.html'
})
export class AppTopbar {
    items!: MenuItem[];

    layoutService = inject(LayoutService);
    readonly auth = inject(AuthService);
    private readonly router = inject(Router);
    loggingOut = false;

    toggleDarkMode() {
        this.layoutService.layoutConfig.update((state) => ({
            ...state,
            darkTheme: !state.darkTheme
        }));
    }

    logout(): void {
        if (this.loggingOut) return;

        this.loggingOut = true;
        this.auth.logout().pipe(
            catchError(() => EMPTY),
            finalize(() => {
                this.loggingOut = false;
                void this.router.navigateByUrl('/auth/login');
            })
        ).subscribe();
    }
}
