# Changelog

## [1.2.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.1.0...v1.2.0) (2023-02-13)


### Features

* improve reliability of certificate refresh ([#599](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/599)) ([e546efb](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/e546efbff967cd6880d2238ba4be2f8711952562))

## [1.1.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.0.0...v1.1.0) (2023-01-10)


### Features

* add support for Python 3.11 ([#577](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/577)) ([b2669be](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b2669bef72ec3a056be0646d92c18acf9a8166c7))
* format `user` argument for automatic IAM authn ([#449](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/449)) ([88f5bcd](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/88f5bcd531aec696998fe8c7485b9291a26f3c2e))


### Bug Fixes

* update TLS protocol for python3.10 ([#575](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/575)) ([bb4ab5d](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/bb4ab5d482d8065e8e866648ffcf43b9b4f8e9a2))

## [1.0.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.9.3...v1.0.0) (2022-12-06)


### Features

* add support for MySQL auto IAM AuthN ([#466](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/466)) ([80644d7](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/80644d7296321d7f00c0dd9b9fd8041bb92bb512))

## [0.9.3](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.9.2...v0.9.3) (2022-11-03)


### Bug Fixes

* set minimum version constraint on cryptography ([#530](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/530)) ([d2dc58f](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/d2dc58f2428ae9e0c2174f7fbd100791a13a45a1))

## [0.9.2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.9.1...v0.9.2) (2022-11-02)


### Bug Fixes

* update cryptography to latest release ([#527](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/527)) ([d6276ec](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/d6276ece7639f6e9fa751345754099a9d52fee2d))

## [0.9.1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.9.0...v0.9.1) (2022-11-01)


### Bug Fixes

* update dependencies to latest versions ([#522](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/522)) ([799f35f](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/799f35f2f74fa187aff5b74267524c1fe397709c))

## [0.9.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.8.1...v0.9.0) (2022-10-18)


### Features

* add `sqladmin_api_endpoint` arg to specify Cloud SQL Admin API endpoint ([#475](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/475)) ([bf1a909](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/bf1a90973cff33c5350b2ced799b5d6089878076))
* add quota_project arg to specify quota and billing project ([#472](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/472)) ([528852a](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/528852a6ec3ecf7a55749697c1245624cc226208))
* downscope token used for IAM DB AuthN ([#488](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/488)) ([d461d75](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/d461d75b0809563b4120aa59ef61fdfdc59c43de))


### Bug Fixes

* throw error if Auto IAM AuthN is unsupported ([#476](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/476)) ([fef0cd7](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/fef0cd7b5fd56016ad220f3c7b8f3abd720ab81f))

## [0.8.1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.8.0...v0.8.1) (2022-09-07)


### Documentation

* add README code sample for Flask-SQLAlchemy and FastAPI ([#432](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/432)) ([fadc357](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/fadc3577b3552dc1650d120c144fdd8ab2500870))

## [0.8.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.7.0...v0.8.0) (2022-07-29)


### Features

* add support for asyncpg driver ([#390](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/390)) ([3170b1f](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/3170b1f568fef860772e8ca7e4f186215bd8a1b5))


### Bug Fixes

* stop event loop on Connector.close ([#410](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/410)) ([5cda924](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/5cda924157a982a2d4bf40e266da4d8f253e3d2c))

## [0.7.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.6.2...v0.7.0) (2022-07-12)


### ⚠ BREAKING CHANGES

* remove deprecated global 'connector.connect' function (#394)

### Features

* remove deprecated global 'connector.connect' function ([#394](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/394)) ([50b81fb](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/50b81fb2325f62231cb15e047d8b9145d95fc711))

## [0.6.2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.6.1...v0.6.2) (2022-06-07)


### Documentation

* add Colab Notebook for Postgres, MySQL and SQL Server ([#372](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/372)) ([a16068f](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/a16068fcb98d46e2642ca521124f3409427c19aa))

### [0.6.1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.6.0...v0.6.1) (2022-05-03)


### Bug Fixes

* update dependencies to latest versions ([#351](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/351)) ([009dfda](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/009dfda4da6848ab36f42cec2effc3ad3925da69))

## [0.6.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.5.2...v0.6.0) (2022-04-05)


### ⚠ BREAKING CHANGES

* deprecate default connect method (#316)

### Features

* add asynchronous interface to Connector ([#280](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/280)) ([9cef59e](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/9cef59eb8534fd0dce425f12dd2fc05a69c27587))
* deprecate default connect method ([#316](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/316)) ([4a543dc](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/4a543dc42938866b63c6887238a1d8867abc5953))
* drop support for Python 3.6 ([#299](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/299)) ([0d63f90](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/0d63f90fd05134165dbde212242b4e9241bbf287))


### Bug Fixes

* resolve TimeoutError and add context manager to Connector ([#309](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/309)) ([372e401](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/372e4012b0b561f9ac9f896ad3ab29a588e067fc))


### [0.5.2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.5.1...v0.5.2) (2022-03-01)


### ⚠ BREAKING CHANGES

* update error messages and doc strings (#276)

### Bug Fixes

* allow support for impersonated credentials via gcloud ([#262](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/262)) ([8b7e5f7](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/8b7e5f70f82e9178f2b209d6aab0791872297f9d))
* remove enable_iam_auth from downstream kwargs and catch error ([#273](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/273)) ([f9576f3](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/f9576f3b1b11e1cfbc71cc440a040799f6d7c267))
* update error messages and doc strings ([#276](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/276)) ([68f37b4](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/68f37b478b35202f6952a1dc0fe6b4bfadf5235e))


### [0.5.1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.5.0...v0.5.1) (2022-02-01)


### Bug Fixes

* make asyncio.Lock() run in background thread ([#252](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/252)) ([f52ba7e](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/f52ba7ec4aa916bc6bb0062eb1b29ac0611b45f5))
* remove token padding strip ([#245](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/245)) ([cb77021](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/cb77021d3c6a3f25a8281f57c481737fd2ee792e))

## [0.5.0](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v0.4.3...v0.5.0) (2022-01-04)


### Features

* add arg for specifying credentials ([#226](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/226)) ([85f5476](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/85f547696b76ad9634273caf68cf6ea93023b3ea))
* add support for python 3.10 ([#227](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/227)) ([8359f85](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/8359f8560a3f6fa532493f1665949bf425a658c3))
* expose Connector object to allow multiple connection configurations. ([#210](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/210)) ([cef1ed1](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/cef1ed143717988ac4252abc64cdc4403971ffb4))


### Bug Fixes

* consolidate to 'ip_type' instead of 'ip_types' for connect args ([#220](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/220)) ([5f9cf58](https://www.github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/5f9cf588d6b553fdac32cc0e9acafea990278dfc))

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
