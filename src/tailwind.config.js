const path = require('path');

module.exports = {
  content: [
    path.join(process.cwd(), 'src/templates/**/*.{html,htm}')
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
