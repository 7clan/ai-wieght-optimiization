/* Trusted minimal React entrypoint. App.jsx comes from measured Qwen slots. */
const React = require('react');
const {createRoot} = require('react-dom/client');
const App = require('../generated/client/App.jsx');

createRoot(document.getElementById('root')).render(React.createElement(App));
