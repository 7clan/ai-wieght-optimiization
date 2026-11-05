// Render untrusted generated React modules ONLY inside a restricted Docker container.
// No generated JavaScript reaches the public static preview itself.
const fs = require('node:fs');
const vm = require('node:vm');
const esbuild = require('esbuild');
const React = require('react');
const ReactDOMServer = require('react-dom/server');

if (!fs.existsSync('/.dockerenv')) throw Error('Preview renderer requires Docker');
if (process.argv.length !== 4) throw Error('Expected input and output paths');
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
if (!input || typeof input.source !== 'string' || input.source.length > 30000 ||
    !Array.isArray(input.examples) || input.examples.length !== 2) {
  throw Error('Invalid preview request');
}

function loadView(source) {
  const compiled = esbuild.transformSync(`${source}\nmodule.exports = ResultView;`, {
    loader:'jsx',format:'cjs',target:'es2022',jsx:'transform',
    jsxFactory:'React.createElement',jsxFragment:'React.Fragment'
  }).code;
  const module = {exports:{}};
  const context = vm.createContext({module,exports:module.exports,
    require(id) {if (id === 'react') return React; throw Error('Module blocked');},
    console:{log(){},error(){},warn(){}}});
  new vm.Script(compiled,{filename:'generated-ui.js'}).runInContext(context,{timeout:1000});
  if (typeof module.exports !== 'function') throw Error('Missing ResultView');
  return module.exports;
}

let result;
try {
  const view = loadView(input.source);
  result = {ok:true,html:input.examples.map(example =>
    ReactDOMServer.renderToStaticMarkup(React.createElement(view,{data:example.expected})))};
} catch (error) {
  result = {ok:false,error:String(error).slice(0,300),html:[]};
}
fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2)+'\n');
