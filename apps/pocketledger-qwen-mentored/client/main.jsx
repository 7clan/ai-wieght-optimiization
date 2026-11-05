const React=require('react');
const {createRoot}=require('react-dom/client');
const {App}=require('./App.jsx');
createRoot(document.getElementById('root')).render(React.createElement(App));
