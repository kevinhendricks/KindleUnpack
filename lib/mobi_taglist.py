#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Functions to handle tag list.

Supported structure is the list consist of single layer tags and comments such as:
[<root>, '<child1/>', '<child2>text</child2>', '<!-- comment -->, '</root>'].
"""

import sys, os, re


re_element = re.compile(r'''
        (?P<comment><!--.*?-->)
    |
        (?P<start_tag><(?P<tag>[^\s/>]+)(.*?>|.*?(?P<empty>/>)))
        (?(empty)|(?P<content>.*?)(?P<end_tag></(?P=tag)>))
    ''', re.X|re.I|re.S)
re_endws = re.compile(r'(?P<end_ws>\s*)(?P<end_bracket>/>|>)')


def convert(src, tag=None):
    # Convert to taglist from src string.
    taglist = []
    if tag is not None:
        pattern = '(?P<start_tag><{0:s}[^>]*>)(?P<child_elements>.*?)(?P<end_tag></{0:s}>)'.format(tag)
        re_tag = re.compile(pattern, re.I|re.S)
        mo_tag = re_tag.search(src)
        if mo_tag is not None:
            start_tag = mo_tag.group('start_tag')
            end_tag = mo_tag.group('end_tag')
            elements = mo_tag.group('child_elements')
            taglist.append(start_tag + '\n')
        else:
            elements = ''
    else:
        mo_tag = None
        elements = src
    pos = 0
    mo_element = re_element.search(elements, pos)
    while mo_element is not None:
        if mo_element.group('comment') is not None:
            taglist.append(mo_element.group())
        elif mo_element.group('start_tag') is not None:
            taglist.append(mo_element.group() + '\n')
        pos = mo_element.end()
        mo_element = re_element.search(elements, pos)
    if mo_tag is not None:
        taglist.append(end_tag + '\n')
    return taglist


def find(srclist, tag, attrib=None, value=None, start=0, end=None, indices=None):
    # Find first index that given conditions match.
    indices = findall(srclist, tag, attrib, value, 1, start, end, indices)
    if len(indices) == 1:
        return indices[0]
    else:
        return None

def findall(srclist, tag, attrib=None, value=None, n=0, start=0, end=None, indices=None):
    # Find indices that given conditions matches.
    if indices is None:
        if end is None:
            end = len(srclist)
        indices = range(start, end)

    if tag[:3] == '!--':
        pattern = r'(<{:})'.format(tag)
    elif tag[:4] == '<!--':
        pattern = r'({:})'.format(tag)
    elif attrib is None:
        pattern = r'<!--.*?-->|(<{:}\s+.*?>)'.format(tag)
    elif value is None:
        pattern = r'<!--.*?-->|(<{:}\s+.*?{:}.*?>)'.format(tag, attrib)
    else:
        pattern = r'<!--.*?-->|(<{:}\s+.*?{:}\s*=\s*"{:}".*?>)'.format(tag, attrib, value)
    re_ = re.compile(pattern, re.S)

    newindices = []
    for i in indices:
        mo = re_.search(srclist[i])
        if mo is not None and mo.group(1) is not None:
            newindices.append(i)
            n -= 1
            if n == 0:
                break
    return newindices

def extract_tags(srclist, indices):
    # Extract tags specified by indices
    new_data = []
    for i, item in enumerate(srclist):
        if i in indices:
            new_data.append(item)
    return new_data

def remove_tags(srclist, indices):
    # Remove tags specified by indices
    new_data = []
    for i, item in enumerate(srclist):
        if i not in indices:
            new_data.append(item)
    return new_data

def remove_attrib(srclist, index, attrib):
    # Return a tag whose specified attribute is removed.
    pattern = r'\s+{:}\s*=\s*"(.*?)"'.format(attrib)
    newdata = re.sub(pattern, '', srclist[index])
    return newdata

def get_attrib(srclist, index, attrib):
    # Get specified attribute value.
    pattern = r'\s+{:}\s*=\s*"(.*?)"'.format(attrib)
    mo = re.search(pattern, srclist[index])
    if mo is not None:
        return mo.group(1)
    else:
        return None

def set_attrib(srclist, index, attrib, value):
    # Return a tag whose specified attribute is added or replaced.
    item = srclist[index]
    repl = ' {:}="{:}"'.format(attrib, value)
    pattern = r'(\s+{:}\s*=\s*".*?")|\s*(/?>)'.format(attrib)
    mo = re.search(pattern, item)
    if mo is not None:
        if mo.group(1) is not None:
            newitem = item[:mo.start()] + repl + item[mo.end():]
        else:
            newitem = item[:mo.start()] + repl + mo.group(2) + item[mo.end():]
    return newitem


def get_content(srclist, index):
    # Get the content of specified tag.
    item = srclist[index]
    mo = re_element.search(item)
    if mo is not None:
        return mo.group('content')
    else:
        return None
    #re_tag = re.compile(r'(<.*?>)(.*?)(</.*>)')
    #mo = re_tag.search(srclist[index])
    #if mo is not None:
    #    return mo.group(2)
    #else:
    #    return None


def set_content(srclist, index, value):
    # Return a tag whose content is added or replaced.
    item = srclist[index]
    mo = re_element.search(item)
    if mo is not None:
        start_tag = mo.group('start_tag')
        mo_ws = re_endws.search(start_tag)
        if mo_ws is not None:
            repl = '{:}>{:}</{:}>'.format(start_tag[:mo_ws.start()], value, mo.group('tag'))
            newitem = item[:mo.start()] + repl + item[mo.end():]
            return newitem
    return item
