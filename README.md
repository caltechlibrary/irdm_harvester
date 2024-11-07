# InvenioRDM Harvester

This is a harvester that can automatically collect and submit works to an
InvenioRDM repository. It currently works with the CaltechAUTHORS repository and looks at CrossRef and ORCID.

[![License](https://img.shields.io/badge/License-BSD--like-lightgrey)](https://choosealicense.com/licenses/bsd-3-clause)
[![Latest
release](https://img.shields.io/github/v/release/caltechlibrary/irdm_harvester.svg?color=b44e88)](https://github.com/irdm_harvester/template/releases)
[![DOI](https://img.shields.io/badge/dynamic/json.svg?label=DOI&query=$.pids.doi.identifier&uri=https://data.caltech.edu/api/records/c14ab-m2d78/versions/latest)](https://data.caltech.edu/records/c14ab-m2d78/latest)

## Table of contents

* [Introduction](#introduction)
* [Installation](#installation)
* [Usage](#usage)
* [Known issues and limitations](#known-issues-and-limitations)
* [Getting help](#getting-help)
* [Contributing](#contributing)
* [License](#license)
* [Authors and history](#authors-and-history)
* [Acknowledgments](#authors-and-acknowledgments)


## Introduction

Currently harvesting:

    - CrossRef by ROR
    - ORCID
    - CrossRef DOIs

## Usage

The harvests are typically run through [GitHub actions](https://github.com/caltechlibrary/irdm_harvester/actions) 
but could also be run on the command line.

You need to have a CaltechAUTHORS token available in the environment variable 
`RDMTOK`. For a CrossRef ROR harvest type

```bash
python harvest.py crossref
```

You can harvest a specific DOI with

```bash
python harvest.py -doi 10.7717/peerj-cs.1023
```

For an ORCID harvest type:

```bash
python harvest.py orcid -orcid 0000-0001-9266-5146
```

For all harvests there is an `-actor` flag, which gets included in the message when the record is added to the queue.

## Installation

For command line use you need the latest version of `irdmtools` installed:

`curl https://caltechlibrary.github.io/irdmtools/installer.sh | sh`

Then install the python requirements with

`pip install -r requirements.txt`

## Known issues and limitations

While this approach should work for any InvenioRDM repository, it has only been tested on 
CaltechAUTHORS. If you're interested in using this with a different repository reach out as we
would be happy to make it a bit more flexible.

Publishers use a wide variety of urls for licenses. We are currently adding
variants to the license.csv file, which is a custom file that connects urls to
the InvenioRDM license names. It is almost certainly incomplete.

## Getting help

Open an issue in the issue tab.

## Contributing

Pull requests are appreciated.

## License

Software produced by the Caltech Library is Copyright © 2022 California Institute of Technology.  This software is freely distributed under a BSD-style license.  Please see the [LICENSE](LICENSE) file for more information.

## Authors and history

GitHub action created by Tom Morrell. Robert Doiel and Tom Morrell wrote
the source irdmtools package.

## Acknowledgments

This work was funded by the California Institute of Technology Library.


<div align="center">
  <br>
  <a href="https://www.caltech.edu">
    <img width="100" height="100" src="https://raw.githubusercontent.com/caltechlibrary/template/main/.graphics/caltech-round.png">
  </a>
</div>
