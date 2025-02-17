import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
  index("routes/home.tsx"),
  route("dashboard", "routes/dashboard/dashboard.tsx"),
  route("sign-in", "routes/auth/sign-in.tsx"),
] satisfies RouteConfig;
