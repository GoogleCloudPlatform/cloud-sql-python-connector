# Changelog

### [0.4.3](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.4.2...v0.4.3) (2021-12-07)


### Documentation

* update README with connection pooling ([#196](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/196)) ([af05cf5](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/af05cf532566d5b8ef2e5930d05a8f4fb5979b48))

### [0.4.2](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.4.1...v0.4.2) (2021-11-02)


### Bug Fixes

* update dependencies to latest versions ([#192](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/192)) ([046838a](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/046838a9a79c44b44032a13e2b711347a1b2d477))

### [0.4.1](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.4.0...v0.4.1) (2021-10-05)


### Bug Fixes

* update dependencies to latest versions ([#176](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/176)) ([03197ab](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/03197aba8b228e9d4baaa092e24ee269f2a81a7c))

## [0.4.0](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.3.0...v0.4.0) (2021-09-02)


### Features

* add rate limiter and force refresh function ([#146](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/146)) ([b390fac](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b390fac132c55a1b5bc4bfa2270b8a9d572c4f53))
* switch development status to beta ([#149](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/149)) ([b415e03](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b415e0380ccbb365640550f03c3bbc9f04d07862))


### Documentation

* Add Support policy to README ([#151](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/151)) ([7dbc4b5](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/7dbc4b53a28b11a3d9a91f5704b7a3fda9cd37e9))

## [0.3.0](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.2.1...v0.3.0) (2021-08-03)


### Features

* support Active Directory auth for Windows ([#131](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/131)) ([66e4e2e](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/66e4e2e6b688bb5e9d7e41b72c5466128b4128e9))


### Bug Fixes

* only replace refresh result if successful or current is invalid ([#135](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/135)) ([9c8ed67](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/9c8ed670377e3b2f9570d0bba7933ca8caf83d0d))
* strip padding from access tokens if present ([#138](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/138)) ([1bc2ee4](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/1bc2ee4753bef515d79fcc15bd2ed804e01c47f2)), closes [#137](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/137)

### [0.2.1](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.2.0...v0.2.1) (2021-07-13)


### Bug Fixes

* update dependencies ([#127](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/127)) ([7e1cccd](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/7e1cccd27826a75b2c74898bf70813621fb0df84))

## [0.2.0](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.1.0...v0.2.0) (2021-06-01)


### Features

* add support for IAM auth with pg8000 driver ([#101](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/101)) ([6703232](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/6703232d6ea624f868e750c8c49c3bb1151f1f1e))


### Bug Fixes

* force use of TLSv1.3 when IAM auth enabled ([#108](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/108)) ([a10aa5a](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/a10aa5ad1f5c4f372914ee11f1180ad0c5f3b703))

## 0.1.0 (2021-05-04)


### Features

* add pg8000 support ([#40](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/40)) ([d810d7d](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/d810d7da9a5048714ad1e1ad28e681e0f679e1a4))
* add pytds support ([#57](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/57)) ([060a78f](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/060a78f906ba833b6e411d3c9ccb3ad41a6db355))
* allow specifying ip address type ([#79](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/79)) ([b3f80c9](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b3f80c94a662169ad555371342b6a3a4871b20de))
* reuse instance connection managers ([#69](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/69)) ([72c05ec](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/72c05ece4f24fe686a0e1ea70b53a4abb827b2d1))
* set User-Agent to include version and SQL driver info ([#54](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/54)) ([851d110](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/851d1109d8f79f7e0a362aeb97d0512d7f162aa6))


### Bug Fixes

* add timeout in InstanceConnectionManager.connect ([#60](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/60)) ([816019b](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/816019bebcb7037ffe81f70ce1dc19c39a8d508b))
* avoid hang on connector.connect ([#27](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/27)) ([e043fe6](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/e043fe68acb9d02b278000e2a4b2317f7ba0ab78))
* cancel all async resources when an ICM is destroyed ([#76](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/76)) ([07de2a2](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/07de2a203fcdba9130ca7013c63d3d778e2c4324))
* correct variable name and credential copying ([#25](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/25)) ([41e317e](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/41e317ecdf6131d933ee455cd68fc4006aac8584))
* generate keys asynchronously ([#59](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/59)) ([56d2c70](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/56d2c70c73e4496d1407d06eb4b398b99d55a3a5))
* use temporary directory instead of tempfile for Windows compatibility ([#84](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/84)) ([ef46607](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/ef46607adbeaaf34811f7352b1bcc6b4c2c80a06))
