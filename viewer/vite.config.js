export default {
  // Pages host path is set per deployment via BASE_PATH (e.g. /golf/);
  // defaults to the original dayne-bonuses Pages location.
  base: process.env.BASE_PATH || "/dayne-bonuses/",
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        colors: 'colors.html',
      },
    },
  },
}
