const path = require('path');

module.exports = {
  content: [
    './templates/**/*.{html,htm}',
    './templates/**/**/*.{html,htm}',
    './static/js/*.js'
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
