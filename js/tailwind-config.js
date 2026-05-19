// js/tailwind-config.js
// Design tokens for SDGNext.
// Loaded BEFORE Tailwind renders so it can extend the default theme.
// See docs/context/ui-tokens.md for the rationale.

tailwind.config = {
  theme: {
    extend: {
      colors: {
        // App shell
        shell: '#1a233a',            // dark navy bg
        'shell-muted': '#94a3b8',    // text on dark

        // Action colors
        primary: '#ec4899',          // pink-500 - commits/important
        'primary-hover': '#db2777',  // pink-600
        secondary: '#6366f1',        // indigo-500 - discovery
        'secondary-hover': '#4f46e5', // indigo-600

        // Semantic
        success: '#10b981',          // emerald-500
        danger: '#ef4444',           // red-500
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif']
      }
    }
  }
};
