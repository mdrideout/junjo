import { type RouteConfig, index, route } from '@react-router/dev/routes'

export default [
  index('routes/home.tsx'),
  route('dashboard', 'routes/dashboard/dashboard.tsx', [
    index('routes/dashboard/index.tsx'),
    route('logs', 'routes/dashboard/logs.tsx'),
  ]),
  route('sign-in', 'routes/sign-in.tsx'),
] satisfies RouteConfig
