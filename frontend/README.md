# BazarStore frontend

This frontend uses Angular 21 and reuses the Sakai template for the BazarStore storefront and backoffice.

## Routes

- `/` opens the public landing page.
- `/backoffice` opens the existing template backoffice dashboard and its pages.
- `/auth/login` opens the BazarStore sign-in page.
- `/auth/register` opens the BazarStore account creation page.

The previous top-level backoffice URLs redirect to their `/backoffice` equivalents.

Login and registration call the FastAPI `/api/v1/auth` endpoints through the local Angular proxy. Access tokens are kept in memory; refresh tokens use the backend's HttpOnly cookie. The development server proxies `/api/v1` to `http://127.0.0.1:8000`; production must route the same path to the API. Google sign-in requires the OAuth Web client ID in `backend/.env` (`GOOGLE_CLIENT_ID`) and `public/runtime-config.local.json` (`googleClientId`), plus the frontend origin authorized in Google Cloud. The tracked `public/runtime-config.json` stays blank as a template; the local override is ignored by Git. Password recovery is not implemented yet.

## Brand assets

Brand images are stored in `assets/images` and copied to `/assets/images` during the Angular build. The BazarStore mark is used in the storefront and backoffice headers, and as the browser favicon.

## Component files

Angular component templates live in adjacent `.html` files, and component logic stays in `.ts` files. Components with custom styles use an adjacent `.scss` file. Keep API access and reusable data operations in services; presentational components do not need an empty service.

## Storefront

The public landing page presents a French e-commerce storefront. Its displayed catalog and USD prices come from the existing demo `ProductService` data; search, category filters, favorites, and cart state are currently local to the page. Checkout, newsletter registration, and live product synchronization are not connected yet.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Karma](https://karma-runner.github.io) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
