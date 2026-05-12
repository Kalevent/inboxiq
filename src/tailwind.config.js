const path = require('path');

module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.{html,htm}',
    './templates/**/**/*.{html,htm}',
    './static/js/*.js'
  ],
  theme: {
    extend: {
      colors: {
        'brand-lavender': '#F1ECFF',
        'brand-ink': {
          DEFAULT: '#0A0A14',
          soft: '#3F3D5C',
        },
        'brand-accent': {
          DEFAULT: '#5B5BD6',
          soft: '#8B82F0',
        },
        'brand-success': '#10B981',
      },
    },
  },
  plugins: [],
};
