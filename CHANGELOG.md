# Changelog

## [1.9.2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.9.1...v1.9.2) (2024-05-14)


### Dependencies

* update dependency cryptography to v42.0.7 ([#1076](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1076)) ([a4aec7e](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/a4aec7ee406cd3e4480833479d394d67c80e9352))

## [1.9.1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.9.0...v1.9.1) (2024-04-17)


### Bug Fixes

* add minimum version for google-auth dep ([#1065](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1065)) ([b13d172](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b13d1723f721a4a19751d4c2550f92656fff0ce4))


### Dependencies

* update dependency aiohttp to v3.9.5 ([#1063](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1063)) ([bd6c323](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/bd6c3239dad0c95ab5e5648a1950b241c4e1ed5b))

## [1.9.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.8.0...v1.9.0) (2024-04-16)


### Features

* add universe domain support to Connector (TPC) ([#1045](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1045)) ([b1e9dee](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b1e9deee216c57e6831162f6aded79511c5e38e3))


### Dependencies

* update dependency aiohttp to v3.9.4 ([#1060](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1060)) ([78b3671](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/78b36715bd2d3a1ca4c4f72295c36b95e360abf1))
* Update dependency google-auth to v2.29.0 ([#1043](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1043)) ([2ac2fd1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/2ac2fd1ab99ee1c0d3a12cd9da7f6820eb0237cc))
* Update dependency pg8000 to v1.31.1 ([#1053](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1053)) ([eaa371d](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/eaa371d95509f97b8951d80046a5a273bece489a))

## [1.8.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.7.0...v1.8.0) (2024-03-12)


### Features

* support `ip_type` as str ([#1029](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1029)) ([e087704](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/e08770422f05c96b1349d1505aab511b15ed1885))


### Bug Fixes

* update create_async_connector args ([#1016](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1016)) ([c3f51a2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/c3f51a24f0fa055fc3459c9170557c6ff15424f5))


### Dependencies

* Update dependency cryptography to v42.0.5 ([#1015](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1015)) ([b47dfef](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b47dfef36e11edd17def5a3b61714256d534ac62))
* Update dependency google-auth to v2.28.2 ([#1034](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1034)) ([bf20bbc](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/bf20bbc3694066e6905b77771ca044421fc3c92f))
* Update dependency pg8000 to v1.30.5 ([#1026](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/1026)) ([e66f4e3](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/e66f4e36235bf09d2a7de20f1a4c1e7158f97a40))

## [1.7.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.6.0...v1.7.0) (2024-02-13)


### Features

* add support for a custom user agent ([#986](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/986)) ([82da410](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/82da41050992de2eddfeae5a81a434192e88d134))
* add support for Python 3.12 ([#905](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/905)) ([7501d17](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/7501d17ee05d41c1e009e4ca44ad7f8edaf18001))


### Dependencies

* Update dependency aiohttp to v3.9.3 ([#993](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/993)) ([168b1f4](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/168b1f43b2d0e4b376d8858aa32bc54e26d3e069))
* Update dependency cryptography to v42.0.2 ([#994](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/994)) ([6b762df](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/6b762df593ffbdc81a7ae98386230af9dc570147))
* Update dependency google-auth to v2.27.0 ([#980](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/980)) ([def011a](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/def011a0f7eee9d6288b441de5df416f429d227f))

## [1.6.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.5.0...v1.6.0) (2024-01-17)


### Features

* add support for domain-scoped projects ([#937](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/937)) ([3d1f36e](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/3d1f36e176d1689380d71fc56f111dbb8de34dcb))


### Dependencies

* Update dependency google-auth to v2.26.2 ([#964](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/964)) ([43d7ad6](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/43d7ad6d7b57454256b933580d51113cc22a2206))
* update dependency pg8000 to v1.30.4 ([#962](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/962)) ([8012c8f](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/8012c8f7d32cd59f851638d7167067f2804125f6))

## [1.5.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.4.3...v1.5.0) (2023-12-12)


### Features

* introduce compatibility with native namespace packages ([#906](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/906)) ([083da11](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/083da1193a838be9f16653f2d4efb4ad8bcfa73a))


### Dependencies

* Update dependency aiohttp to v3.9.1 ([#916](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/916)) ([b6f9485](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/b6f9485d644b6ff3203ebed175ec8a3754bf319b))
* Update dependency cryptography to v41.0.7 ([#917](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/917)) ([43e22e1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/43e22e1e03c5066c328729920b5f8a8bb6480d07))
* Update dependency google-auth to v2.25.2 ([#929](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/929)) ([24439a9](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/24439a991df189ebe252415f369ff4ce93a42d58))

## [1.4.3](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.4.2...v1.4.3) (2023-11-15)


### Bug Fixes

* use IAM login creds in expiration logic ([#898](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/898)) ([7f8a3a4](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/7f8a3a46ce754de7ffcf8adb58a075cb43c987f4))
* Use utcnow() in refresh calculation ([#890](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/890)) ([469ed04](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/469ed044c45947f8153133a10753eaf078b133dd))


### Dependencies

* Update dependency asyncpg to v0.29.0 ([#887](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/887)) ([9c566ea](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/9c566eaa3ed08874c6653d0ce35f92c3ab99888c))
* Update dependency cryptography to v41.0.5 ([#874](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/874)) ([9f9dd0d](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/9f9dd0dc5ac43fa9402ccb7477b8972a74fa3703))
* Update dependency pg8000 to v1.30.3 ([#882](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/882)) ([13e9d31](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/13e9d3132290989a788157f1d91b83103ccb3764))

## [1.4.2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.4.1...v1.4.2) (2023-10-09)


### Dependencies

* Update actions/checkout action to v3.6.0 ([#829](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/829)) ([f6c1fea](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/f6c1fea75527f28c4b150720b7367001767a9f6f))
* Update actions/checkout action to v4 ([#837](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/837)) ([0f570a6](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/0f570a66e2416cacb987b62a84b1f9547ae71e7a))
* Update actions/checkout action to v4.1.0 ([#855](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/855)) ([0566b15](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/0566b1507638f909ef3081287c8531479787c3e1))
* Update actions/setup-python action to v4.7.1 ([#858](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/858)) ([1085306](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/108530617916fa1ec8462cc6c6fcceb77fc8c73f))
* Update actions/upload-artifact action to v3.1.3 ([#838](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/838)) ([3238c96](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/3238c96735fed1b9f124c885923f40cd1208300e))
* Update dependencies for github ([#863](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/863)) ([cad15e2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/cad15e2f5afe29c8248d61f6bf18e81ae43d1395))
* Update dependency aiohttp to v3.8.6 ([#864](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/864)) ([0d4cf17](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/0d4cf175dfd8b2ec4716c048283fb713f20d211a))
* Update dependency black to v23.9.1 ([#840](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/840)) ([89e90fd](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/89e90fdc8879e60c22e734cac338d5e5a857dbb6))
* Update dependency cryptography to v41.0.4 ([#851](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/851)) ([c700e9b](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/c700e9b984e6660c3058d707808158e0225fe506))
* Update dependency pg8000 to v1.30.2 ([#848](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/848)) ([62079f7](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/62079f74cc742ec9882db518a58ae7a1f65822d0))
* Update dependency pytest to v7.4.2 ([#835](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/835)) ([3d05557](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/3d05557e66e8552f50f0e9199c3c96fd130b8e0d))
* Update dependency SQLAlchemy to v2.0.21 ([#849](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/849)) ([f5e9c2f](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/f5e9c2f6ba39a4fed68874b0eb97490676534a9c))
* Update dependency types-mock to v5.1.0.2 ([#836](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/836)) ([9a57a41](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/9a57a41a76c4c7d2fcf94bfbbb54e5575802dc57))
* Update github/codeql-action action to v2.21.5 ([#832](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/832)) ([6c7c322](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/6c7c3229190f46d5e30e48ffa17043029b234124))
* Update github/codeql-action action to v2.21.6 ([#841](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/841)) ([71b9347](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/71b9347e265398ae2c3a0db4c1a7595ac199b9bf))
* Update github/codeql-action action to v2.21.7 ([#847](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/847)) ([53a19ad](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/53a19adc5e73a9d0d7ce949e21cb794d67507345))
* Update github/codeql-action action to v2.21.8 ([#850](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/850)) ([2bd4f3a](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/2bd4f3ae98168f3d194195807e7d9863fc426bc6))
* Update github/codeql-action action to v2.21.9 ([#857](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/857)) ([28f07ae](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/28f07ae5c3125a576933dd44ab08a1afbcf71e92))

## [1.4.1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.4.0...v1.4.1) (2023-08-18)


### Bug Fixes

* re-use existing connections on force refresh ([#828](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/828)) ([f98c1b6](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/f98c1b6e29a2328a1911fda10ac5ce463ec70197))

## [1.4.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.3.0...v1.4.0) (2023-08-08)


### Features

* configure pg8000 connection with SSLSocket ([#789](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/789)) ([a6433b9](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/a6433b98323f91378cdb285f9c732dd45a7376a3))


### Dependencies

* Update dependency aiohttp to v3.8.5 ([#801](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/801)) ([7ed23d0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/7ed23d00fabeb6cda498c64bb994fe7e6a0f4a2e))
* Update dependency cryptography to v41.0.3 [SECURITY] ([#810](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/810)) ([d11b3a5](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/d11b3a58090b923c27539bae20051f957f34fcde))
* Update dependency pg8000 to v1.30.1 ([#808](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/808)) ([c4cd9bc](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/c4cd9bc5bb64bb170eba7d30c0f303e8b839beef))
* Update dependency python-tds to v1.13.0 ([#818](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/818)) ([65cccf3](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/65cccf361057cff1f4b676474b7e1798f66d9408))

## [1.3.0](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.2.4...v1.3.0) (2023-07-11)


### Features

* add support for PSC connections ([#766](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/766)) ([c238fe3](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/c238fe34e7e18a82c53112c56c141fdf38649523))
* remove support for Python 3.7 ([#761](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/761)) ([5b8a172](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/5b8a172e23e322ef6b425740cab4bed0a308c171))


### Documentation

* update getconn in README samples ([#773](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/773)) ([179c06e](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/179c06e025d1e7a46e4d82bfae19bd21a03b160d))


### Dependencies

* Update dependency asyncpg to v0.28.0 ([#785](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/785)) ([036982e](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/036982e9bf11cc441a30e6c1922cf132ed0a8daa))
* Update dependency cryptography to v41.0.2 ([#790](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/790)) ([869fb49](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/869fb490e193ca9fb7f10a709d2d96648c5b3eb9))
* Update dependency google-auth to v2.21.0 ([#781](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/781)) ([be4b492](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/be4b4924b6adef227eeda03bfeed52bf2e83abf1))
* Update dependency pg8000 to v1.29.8 ([#778](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/778)) ([46e8637](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/46e8637b234ec41521695228d9e1d919d61d58bd))
* Update dependency PyMySQL to v1.1.0 ([#780](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/780)) ([dd3fa64](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/dd3fa642eb9aedc47b4893807f2de8284e4441f3))

## [1.2.4](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.2.3...v1.2.4) (2023-06-13)


### Bug Fixes

* improve `timeout` handling ([#760](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/760)) ([723b6f1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/723b6f1b7996dbc8a14993b4b630809585edd245))


### Dependencies

* Update dependency cryptography to v41.0.1 ([#749](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/749)) ([e89755c](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/e89755c0ca10bf7463787a0474d137896457c409))
* Update dependency google-auth to v2.19.1 ([#751](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/751)) ([eee33ae](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/eee33ae9e0fcdfef2cf8934490e4587eabcd77b4))
* Update dependency pg8000 to v1.29.6 ([#746](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/746)) ([47d6d87](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/47d6d87b7b92413037aeddacebc36e2a78d57a08))
* Update dependency Requests to v2.31.0 ([#733](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/733)) ([c18869d](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/c18869ddf1daecfcd5d8c6ee62a4ae679db7a6df))


### Documentation

* document SQLAlchemy async connection pooling ([#758](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/758)) ([bb1c72a](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/bb1c72a74f879e0752e6156cd1c0335a196ca882))

## [1.2.3](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.2.2...v1.2.3) (2023-05-08)


### Dependencies

* Update dependency cryptography to v40.0.2 ([#705](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/705)) ([5544086](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/55440868ffbea4ad653af9412aaeb762eb754277))
* Update dependency google-auth to v2.17.3 ([#698](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/698)) ([37a5150](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/37a51509153e6353c9458dcbf9bc1100a963ddc2))
* Update dependency Requests to v2.30.0 ([#717](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/717)) ([db4fbcb](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/db4fbcbfe3b35a64a3935320e650da36e1fd9e2d))

## [1.2.2](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.2.1...v1.2.2) (2023-04-10)


### Dependencies

* Update dependency cryptography to v40 ([#669](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/669)) ([e95fa98](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/e95fa985cb720be83b450eefce162d9c12d5800f))
* Update dependency google-auth to v2.17.2 ([#690](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/690)) ([02bf543](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/02bf54352e1a0409771668a4c24aae881c308a8b))
* Update dependency PyMySQL to v1.0.3 ([#677](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/677)) ([4bb8751](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/4bb8751ec7a50c28d973e28bcc89851643354401))

## [1.2.1](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/compare/v1.2.0...v1.2.1) (2023-03-14)


### Bug Fixes

* update dependencies to latest versions ([#646](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/issues/646)) ([d758987](https://github.com/GoogleCloudPlatform/cloud-sql-python-connector/commit/d758987ac0cc0bf2e978a4c4b50a3b0809f457f0))

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
