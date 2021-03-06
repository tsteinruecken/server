# -*- coding: utf-8 -*-
from viur.core.bones import relationalBone

from viur.core import request


class treeDirBone(relationalBone):

	def __init__(self, kind=None, format="$(dest.name)", *args, **kwargs):
		if kind and not kind.endswith("_rootNode"):
			kind += "_rootNode"
		super(treeDirBone, self).__init__(kind=kind, format=format, *args, **kwargs)
