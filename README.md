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
       pip install git+https://github.com/jlo031/CDSE

2. **Local installation**

       # clone the repository
       git clone git@github.com:jlo031/CDSE

   Change into the main directory of the cloned repository (it should contain the *setup.py* file) and install the library:

       # installation
       pip install .


### Usage
The main search and download functions are implemnted in the *CDSE.search_and_download.py* module.  
The download functions require your CDSE user credentials. It is recommended to store them in a hidden *.env* file in your working directory:

    # contents of your '.env' file
    CDSE_USER='your-CDSE-user-name'
    CDSE_PASSWORD='your-CDSE-password'

You can now read your username and passord from this file using the *python-dotenv* package using a function implemented in *CDSE.utils*:

    # read your user credentials from '.env'
    import CDSE.utils as CDSE_utils
    username, password = CDSE_utils.get_user_and_passwd('path-to-your-.env-file')



You can search for specific products by name, products intersecting with given lat/lon coordinates, or products intersecting with an area of interest saved in geoJSON format.

Below is an example of how to search and download a specific product by name. For further examples and tests of the code, refer to the *examples* folder.

    # import main module
    import CDSE.search_and_download as CDSE_sd

    # search for specific product by name
    product_name = 'S1A_EW_GRDM_1SDH_20220602T073727_20220602T073831_043481_05310C_53F3'
    response_json = CDSE_sd.search_CDSE_catalogue_by_name(product_name)

    # download the found product
    product = response_json['value'][0]
    download_dir = 'path-to-your-download-directory'
    CDSE_sd.download_product_from_cdse(product, download_dir, username, password)








