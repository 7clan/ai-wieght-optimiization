const {defineConfig} = require('vite');
const path=require('node:path');
module.exports=defineConfig({root:__dirname,plugins:[],
  build:{outDir:path.join(__dirname,'dist'),emptyOutDir:true},
  server:{host:'0.0.0.0'}});
