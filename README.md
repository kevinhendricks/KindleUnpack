KindleUnpack
============

python based software to unpack Amazon / Kindlegen generated ebooks

KindleUnpack unpacks a non-DRM Kindle/MobiPocket ebook into its component parts 
which change depending on the type of Kindle/Mobi ebook being processed

	- MobiPocket and early Kindle version 7 or less ebooks are unpacked to the 
            original html 3.2 and images folder that can then be edited and reprocessed by 
            MobiPocketCreator.

	- Kindle Print Replica ebook as unpacked to the original PDF and any associated images.

	- Kindle KF8 only ebooks (.azw3) are unpacked into an epub-like structure that may or 
            may not be a fully valid epub depending on if a fully valid epub was 
            originally provided to kindlegen as input.  NOTE: The generated epub should be
            validated using an epub validator and should changes be needed, it should load
            properly into Sigil and Calibre either of which can be used to edit the result
            to create a fully valid epub.

	- Newer Kindle ebooks which have both KF8 and older versions inside are unpacked into 
            two different parts: the first being the older MobiPocket format ebook parts 
            and the second being an epub-like structure that can be edited using Sigil

The KindleUnpack program currently requires Python 2.7.X to function properly. But work is 
underway to create a version that will work on both Python 2.7.X and Python 3.4.X or later.

On Windows machines we strongly recommend you install the free version of ActiveState's 
Active Python 2.7.X or later as it properly installs all of the required parts including 
the tk widget kit and updates the system path on Windows machines.  The official installer 
from python.org sometimes does not properly handle this for Windows machines.

On Mac OS X 10.6.X and later and almost all recent Linux versions, the required version 
of Python is already installed as part of the official OS installation so Mac OS X and 
Linux users need install nothing extra.

To install KindleUnpack, simply find a nice location on your machine and fully unzip it.  
Do not move the KindleUnpack.pyw program away from its associated "lib" folder.  If you 
have a proper Python 2.7 or later installation on your machine, you should be able to 
simply double-click the KindleUnpack.pyw icon and the gui interface should start

If you would prefer a command-line interface, simply look inside KindleUnpack's "lib" 
folder for the KindleUnpack.py python program and its support modules.  You should 
then be able to run KindleUnpack.py by the following command:


python kindle_unpack.py [-r -s -d -h -i] [-p APNX_FILE] INPUT_FILE OUTPUT_FOLDER

where you replace:

   INPUT_FILE      - path to the desired Kindle/MobiPocket ebook

   OUTPUT_FOLDER   - path to folder where the ebook will be unpacked

Options:
    -h               print this help message

    -i               use HDImages to overwrite lower resolution versions, if present

    -s               split combination mobis into older mobi and mobi KF8 ebooks

    -p APNX_FILE     path to a .apnx file that contains real page numbers associated
                         with an azw3 ebook (optional).  Note: many apnx files have 
                         arbitrarily assigned page offsets that will confuse KindleUnpack 
                         if used

   --epub_version=   specify epub version to unpack to: 2, 3 or A (for automatic) or 
                        F for Force to epub2, default is 2

    -r               write raw data to the output folder

    -d               dump headers and other debug info to output and extra files



Please report any bugs or comments/requests our sticky forum on the Mobileread website.  
It can be found at http://www.mobileread.com/forums.  

Look under E-Book Formats > Kindle Formats > KindleUnpack (MobiUnpack).


License Information

KindleUnpack
    Based on initial mobipocket version Copyright © 2009 Charles M. Hannum <root@ihack.net>
    Extensive Extensions and Improvements Copyright © 2009-2014 
         By P. Durrant, K. Hendricks, S. Siebert, fandrieu, DiapDealer, nickredding, tkeo.
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, version 3.
