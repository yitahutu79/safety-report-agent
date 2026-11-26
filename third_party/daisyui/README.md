# daisyUI selective CSS reuse

Upstream: https://github.com/saadeghi/daisyui
Version: 5.8.3 (MIT). License retained in LICENSE.

Two unchanged distributable components are bundled locally:

- https://cdn.jsdelivr.net/npm/daisyui@5.8.3/components/kbd.css -> web/vendor/daisyui-kbd.css
  SHA-256 f400338a69f36cf88f209e63ac2396f54b73202b2c03483cea847b22089ff62a
- https://cdn.jsdelivr.net/npm/daisyui@5.8.3/components/badge.css -> web/vendor/daisyui-badge.css
  SHA-256 33272ca4a64fe62ea4b3d82de3f0399e6328524eb84d50d226b1767b0ec35b01

Used for keyboard-shortcut labels and live category counts. Local semantic variables and layout adaptations are in component-experience.css. No Tailwind runtime, CDN requests or full CSS reset is added. Other component libraries named in the project research are design/interaction references, not installed React runtimes.
