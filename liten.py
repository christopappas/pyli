#!/usr/bin/env python
#11/24/07
#Liten 0.1.3
#A Deduplication Tool
#Author:  Noah Gift
#License:  MIT License
#http://www.opensource.org/licenses/mit-license.php
#Copyright (c) 2007, Noah Gift

"""
A deduplication command line tool and library.  An relatively efficient
algorithm based on filtering like sized bytes, and then performing a full
md5 checksum, is used to determine duplicate files/file objects.

Example CLI Usage:

liten.py -s 1 /mnt/raid         is equal to liten.py -s 1MB /mnt/raid
liten.py -s 1bytes /mnt/raid
liten.py -s 1KB /mnt/raid
liten.py -s 1MB /mnt/raid
liten.py -s 1GB /mnt/raid
liten.py -s 1TB /mnt/raid

Example Library Usage:

Currently Liten is optimized for CLI use, but more library friendly changes
are coming.

    >>> Liten = LitenBaseClass(spath='testData')
    >>> dupeFileOne = 'testData/testDocOne.txt'
    >>> checksumOne = Liten.createChecksum(dupeFileOne)
    >>> dupeFileTwo = 'testData/testDocTwo.txt'
    >>> checksumTwo = Liten.createChecksum(dupeFileTwo)
    >>> nonDupeFile = 'testData/testDocThree_wrong_match.txt'
    >>> checksumThree = Liten.createChecksum(nonDupeFile)
    >>> checksumOne == checksumTwo
    True
    >>> checksumOne == checksumThree
    False

Tests:

 * Run Doctests:  ./liten -t or --test
 * Run test_liten.py

Display Options:

STDOUT:

stdout will show you duplicate file paths and sizes such as:

Printing dups over 1 MB using md5 checksum: [SIZE] [ORIG] [DUP]
7 MB  Orig:  /Users/ngift/Downloads/bzr-0-2.17.tar Dupe:  /Users/ngift/Downloads/bzr-0-4.17.tar

REPORT:

A report named LitenDuplicateReport?.txt will be created in your current working directory.

Duplicate Version,     Path,       Size,       ModDate
Original, /Users/ngift/Downloads/bzr-0-2.17.tar, 7 MB, 07/10/2007 01:43:12 AM
Duplicate, /Users/ngift/Downloads/bzr-0-3.17.tar, 7 MB, 07/10/2007 01:43:27 AM

KNOWN ISSUES:

Very large binary files, .vmdk for example, > 4 GB, can eat up all available memory.
Working on solution for 0.1.4

"""

import os
import datetime
import re
import sys
import string
import time
import optparse
import md5
import logging


class LitenBaseClass(object):
    """
    A base class for searching a file tree.

    Contains several methods for analyzing file objects.
    Main method is diskWalker, which walks filesystem and determines
    duplicates.

    >>> Liten = LitenBaseClass(spath='testData')
    >>> fakePath = 'testData/testDocOne.txt'
    >>> modDate = Liten.makeModDate(fakePath)
    >>> createDate = Liten.makeCreateDate(fakePath)
    >>> dupeFileOne = 'testData/testDocOne.txt'
    >>> checksumOne = Liten.createChecksum(dupeFileOne)
    >>> badChecksumAttempt = Liten.createChecksum('fileNotFound.txt')
    IO error for fileNotFound.txt
    >>> dupeFileTwo = 'testData/testDocTwo.txt'
    >>> checksumTwo = Liten.createChecksum(dupeFileTwo)
    >>> nonDupeFile = 'testData/testDocThree_wrong_match.txt'
    >>> checksumThree = Liten.createChecksum(nonDupeFile)
    >>> checksumOne == checksumTwo
    True
    >>> checksumOne == checksumThree
    False
    >>> SearchDate = Liten.createSearchDate()
    >>> createExt = Liten.createExt(dupeFileOne)
    >>> createExt
    '.txt'

    """

    def __init__(self, spath=None,
                    fileSize='1MB',
                    reportPath="LitenDuplicateReport.txt",
                    verbose=True):
        self.spath = spath
        self.reportPath = reportPath
        self.fileSize = fileSize
        self.verbose = verbose
        self.checksum_cache_key = {}
        self.checksum_cache_value = {}
        self.confirmed_dup_key = {}
        self.confirmed_dup_value = {}
        self.byte_cache = {}

    def log(self):
        """Method that actually performs logging."""

        logging.basicConfig(level = logging.DEBUG,
                            format = '%(asctime)s %(levelname)s %(message)s',
                            filename = "/tmp/LitenLog.txt",
                            filemode = 'w')
        return logging

    def makeModDate(self,path):
        """
        Makes a modification date object
        """
        mod = time.strftime("%m/%d/%Y %I:%M:%S %p",time.localtime(os.path.getmtime(path)))
        return mod

    def makeCreateDate(self, path):
        """
        Makes a creation date object
        """
        create = time.strftime("%m/%d/%Y %I:%M:%S %p",time.localtime(os.path.getctime(path)))
        return create

    def createChecksum(self, path):
        """
        Reads in file.  Creates checksum of file line by line.
        Returns complete checksum total for file.
        """
        try:
            fp = open(path)
            checksum = md5.new()
            for line in fp:
                checksum.update(line)
            fp.close()
            checksum = checksum.digest()
        except IOError:
            print "IO error for %s" % path
            checksum = None

        return checksum

    def createSearchDate(self):
        now = datetime.datetime.now()
        date = now.strftime("%Y%m%d")
        return date

    def createExt(self, file):
        """
        takes a file on a path and returns extension
        """
        (shortname, ext) = os.path.splitext(file)
        return ext

    def sizeType(self):
        """
        Calculates size based on input.

        Uses regex search of input to determine size type.
        """
        fileSize = self.fileSize

        patterns = {'bytes': '1',
                    'KB': '1024',
                    'MB': '1048576',
                    'GB': '1073741824',
                    'TB': '1099511627776'}

        #Detects File Size Type, Strips off Characters
        #Converts value to bytes
        for key in patterns:
            value = patterns[key]
            try:
                if re.search(key, fileSize):
                    #print "Key: %s Filesize: %s " % (key, fileSize)
                    #print "Value: %s " % value
                    byteValue = int(fileSize.strip(key)) * int(value)
                    #print "Converted byte value: %s " % byteValue
                else:
                    byteValue = int(fileSize.strip()) * int(1048576)
                    #print "Converted byte value: %s " % byteValue
            except:
                pass    #Note this gets caught using optparse which is cleaner
        return byteValue

    def diskWalker(self):
        """Walks Directory Tree Looking at Every File, while performing a duplication match algorithm.

        Algorithm:
        This divides directory walk into doing either a more informed search if byte in key repository,
        or appending byte_size to list and moving to next file.  A md5 checksum is made of any file that has
        a byte size that has been found before.  The checksum is then used as the basis to determine duplicates.

        (Note that test includes .svn directory)

        >> from liten import LitenBaseClass
        >>> Liten = LitenBaseClass(spath='testData', verbose=False)
        >>> Liten.diskWalker()


        """
        #Local Variables
        report = open(self.reportPath, 'w')
        main_path = os.walk(self.spath)
        byteSizeThreshold = self.sizeType()
        dupNumber=0
        byte_count=0
        record_count=0

        #times directory walk
        start = time.time()

        if self.verbose:
            print "Printing dups over %s bytes using md5 checksum: [SIZE] [ORIG] [DUP]" % self.fileSize
        for root, dirs, files in main_path:
            for file in files:
                path = os.path.join(root,file)      #establishes full path
                if os.path.isfile(path):            #ignores symbolic links
                    self.byte_size = os.path.getsize(path)
                    record_count += 1                       #gets number of file examined
                    if self.byte_size >= byteSizeThreshold:      #Note create hook for CLI later input size, patt match etc.
                        if self.byte_cache.has_key(self.byte_size):

                            #start debug logging
                            self.log().debug('Doing checksum on %s' % path)

                            #print "Doing checksum on %s" % path
                            checksum = self.createChecksum(path)

                            #checking to see if file has same checksum as checksum cache
                            if self.checksum_cache_key.has_key(checksum):
                                byte_count += self.byte_size                     #accumulates bytes of duplicates found
                                dupNumber += 1                              #accumulates a dupNumber record

                                #print byte_count/1048576, " MB's wasted"
                                #since we have a match, creating record with match partner and printing match original.
                                #grab original file path from checksum_cache dict

                                orig_path = self.checksum_cache_key[checksum]['fullPath']
                                orig_mod_date = self.checksum_cache_key[checksum]['modDate']
                                if self.verbose:
                                    print self.byte_size/1048576, "MB ", "Orig: ", orig_path, "Dupe: ", path

                                #write out to report
                                report.write("Duplicate Version,     Path,       Size,       ModDate\n")
                                #Write original line
                                report.write("%s, %s, %s MB, %s\n" % ("Original", orig_path, self.byte_size/1048576, orig_mod_date))

                                #Gets Duplicates Modification Date
                                dupeModDate = self.makeCreateDate(path)

                                #Write duplicate line
                                report.write("%s, %s, %s MB, %s\n" % ("Duplicate", path, self.byte_size/1048576, dupeModDate))

                                #create original's record

                                #debugging--This is very expensive:
                                self.confirmed_dup_key[orig_path] = self.checksum_cache_value          #Note this is a good spot for the dup rec count


                                #print "Original Duplicate: ", self.confirmed_dup_key[path]
                                #print confirmed_[checksum], self.byte_size/1048576, "MB ", self.makeCreateDate(path),  " ORIG"

                                #setrecord for duplicate match stored
                                confirmed_dup_value = {'fullPath': path,                    #duplicate code clean up later.
                                                        'modDate': modDate,
                                                        'dupNumber': dupNumber,
                                                        'searchDate': searchDate,
                                                        'checksum': checksum,
                                                        'bytes': self.byte_size,
                                                        'fileType': fileType,
                                                        'fileExt': fileExt}
                                self.confirmed_dup_key[path]=confirmed_dup_value
                                #print "duplicate file: ", path
                                #if self.verbose:
                                #    print self.checksum_cache[checksum], self.byte_size/1048576, "MB ", self.makeCreateDate(path),  " ORIG"
                                    #print path, self.byte_size/1048576, "MB ", self.makeCreateDate(path), " DUP"

                            else:
                                #get checksum of file that has a byte dupe match
                                checksum = self.createChecksum(path)
                                createDate = self.makeCreateDate(path)
                                modDate = self.makeCreateDate(path)                #Note I already grabbed this earlier
                                searchDate = self.createSearchDate()
                                fileExt = self.createExt(file)
                                fileType = None
                                self.checksum_cache_value = {'fullPath': path,                       #duplicate code clean up later.
                                                                'modDate': modDate,
                                                                'dupNumber': dupNumber,
                                                                'searchDate': searchDate,
                                                                'checksum': checksum,
                                                                'bytes': self.byte_size,
                                                                'fileType': fileType,
                                                                'fileExt': fileExt}

                                self.checksum_cache_key[checksum]=self.checksum_cache_value       #creating first checksum only dict.
                                #print "not a Dupe? ", path
                        else:
                            self.log().debug('Length of byte size matches in queue %s' % self.byte_cache)
                            self.byte_cache[self.byte_size] = None
                            #pickle out file_system_record

        if self.verbose:
            print "\n"
            print "LITEN REPORT: \n"
            print "Search Path:                 ", self.spath
            #print "Total Files Searched:        ", record_count
            #print "Duplicates Found:            ", len(self.confirmed_dup_key)
            print "Wasted Space in Duplicates:  ", byte_count/1048576, " MB"
            print "Report Generated at:         ", self.reportPath
            #get finish time
            end = time.time()
            timer = end - start
            timer = long(timer/60)
            print "Search Time:                 ", timer, " minutes\n"

        return  self.confirmed_dup_key   #Note returns a dictionary of all duplicate records

class LitenController(object):
    """
    Controller for DiskStat Command Line Tool.
    Handles optionparser parameters and setup.
    """

    def run(self):
        """Run method for Class"""
        p = optparse.OptionParser(description='A tool to examine your filesystem and find duplicates using md5 checksums.',
                                                prog='liten',
                                                version='liten 0.1.2',
                                                usage= '%prog [starting directory] [options]')
        p.add_option('--size', '-s',
                    help='File Size Example:  10bytes, 10KB, 10MB,10GB,10TB, or plain number defaults to MB (1 = 1MB)',
                    default='1MB')
        p.add_option('--quiet', '-q', help='Suppresses all STDOUT.')
        options, arguments = p.parse_args()

        #Note this can be cleaned up. Too many conditionals.
        if len(arguments) == 1:
            spath = arguments[0]
            if options.quiet:
                start = LitenBaseClass(spath, verbose=False)
            elif options.size:  #This input gets stripped into a meaningful chunks
                fileSize  = options.size
                verbose = True
                if options.quiet:
                    verbose = False
                start = LitenBaseClass(spath, fileSize, verbose=verbose)
                try:
                    value = start.diskWalker()
                except UnboundLocalError:       #Here I catch bogus size input exceptions
                    p.print_help()
            elif options.doctest:
                _test()
            else:
                start = LitenBaseClass(spath)
                value = start.diskWalker()
            #for key in value:
            #    print key
        else:
            p.print_help()  #note if nothing is specified on the command line or if more than one parameter is specified, help is printed

def _main():
    """Runs liten."""
    create = LitenController()
    create.run()
def _test():
    """Runs doctests."""
    import doctest
    doctest.testmod(verbose=True)

if __name__ == "__main__":
    """Looks for -v to run doctests else runs main application"""
    try:
        if sys.argv[1] == "-t":
           _test()
        else:
            _main()
    except:
        _main()

