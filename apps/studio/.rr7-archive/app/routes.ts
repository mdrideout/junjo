import { type RouteConfig, index, route } from '@react-router/dev/routes'

export default [
  index('routes/home.tsx'),
  route('dashboard', 'routes/dashboard/dashboard.tsx', [
    index('routes/dashboard/index.tsx'),
    route('logs', 'routes/dashboard/logs.tsx'),
  ]),
  route('sign-in', 'routes/sign-in/sign-in.tsx', [index('routes/sign-in/index.tsx')]),

  // API routes
  route('api/hash-password', 'routes/api/hash-password.ts'),
] satisfies RouteConfig
