const path = require('path');

module.exports = {
  darkMode: 'class',
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
