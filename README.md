# CDSE

Library for search and download of satellite data from the [Copernicus Data Space Ecosystem (CDSE)](https://dataspace.copernicus.eu/), using the [OpenSearch catalogue](https://documentation.dataspace.copernicus.eu/APIs/OpenSearch.html).

To use the download functions in this library, you must [register](https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/auth?client_id=cdse-public&response_type=code&scope=openid&redirect_uri=https%3A//dataspace.copernicus.eu/account/confirmed/1) a (free) account on the CDSE website.


### Preparation
Create anaconda environment:

    # create and activate new environment
    conda create -y --name CDSE python=3.12
    conda activate CDSE

    # install requirements
    conda install -y -c conda-forge loguru requests geojson geomet python-dotenv shapely
    pip install ipython

### Installation
You can install this library directly from github (1) or locally after cloning (2).  
For both installation options, first set up the environment as described above.

1. **Installation from github**

       # install this package
       pip install git+https://github.com/jlo031/cdse

2. **Local installation**

       # clone the repository
       git clone git@github.com:jlo031/cdse

   Change into the main directory of the cloned repository (it should contain the *setup.py* file) and install the library:

       # installation
       pip install .


### Usage
The main search and download functions are implemnted in the *CDSE.search_and_download.py* module.  
The download functions require your CDSE user credentials. It is recommended to store them in a hidden *.env* file in your working directory:

    # contents of your '.env' file
    CDSE_USER='your-CDSE-user-name'
    CDSE_PASSWORD='your-CDSE-password'

TO DO:
use cdse.catalogue to search for data and cdse.download to download products.




