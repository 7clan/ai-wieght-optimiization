# Vendored browser runtimes (trusted infrastructure)

These two pinned files are the only third-party code served by the generated
app pages in this gallery. They are NOT model output and are never attributed
to Qwen.

| File | Origin | Version | License | SHA-256 |
| --- | --- | --- | --- | --- |
| `react.production.min.js` | https://unpkg.com/react@18.3.1/umd/react.production.min.js | React 18.3.1 UMD | MIT | `d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd` |
| `react-dom.production.min.js` | https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js | ReactDOM 18.3.1 UMD | MIT | `35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d` |

Why 18.3.1 UMD while the Docker evaluator uses React 19.1.1: React 19 no
longer publishes UMD builds, and the deployed static pages need a self-contained
classic `React`/`ReactDOM` global runtime with no external CDN dependency. The
generated components target the common `React.useState` / `React.useEffect`
API, identical across both versions. Every gallery page states this in its
disclosure ledger.
