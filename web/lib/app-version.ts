import pkg from "../package.json";

export const APP_VERSION =
  process.env.NEXT_PUBLIC_APP_VERSION ||
  process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA?.slice(0, 7) ||
  `v${pkg.version}`;
