# -*- coding: utf-8 -*-
from viur.core.bones import relationalBone


class treeItemBone(relationalBone):
	def __init__(self, *args, **kwargs):
		super(treeItemBone, self).__init__(*args, **kwargs)
