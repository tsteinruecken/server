# -*- coding: utf-8 -*-
import logging, sys
from datetime import datetime
from time import time

from viur.core import db, utils, errors, conf, request, securitykey
from viur.core import forcePost, forceSSL, exposed, internalExposed
from viur.core.bones import baseBone, keyBone, numericBone
from viur.core.prototypes import BasicApplication
from viur.core.skeleton import Skeleton, skeletonByKind
from viur.core.tasks import callDeferred
from enum import Enum


class TreeSkel(Skeleton):
	parententry = keyBone(descr="Parent", visible=False, indexed=True, readOnly=True)
	parentrepo = keyBone(descr="BaseRepo", visible=False, indexed=True, readOnly=True)
	sortindex = numericBone(descr="SortIndex", mode="float", visible=False, indexed=True, readOnly=True, max=pow(2, 30))

	def preProcessSerializedData(self, dbfields):
		if not ("sortindex" in dbfields and dbfields["sortindex"]):
			dbfields["sortindex"] = time()
		return dbfields


class TreeType(Enum):
	Node = 1
	Leaf = 2


class Tree(BasicApplication):
	"""
	Tree is a ViUR BasicApplication.

	In this application, entries are hold in directories, which can be nested. Data in a Tree application
	always consists of nodes (=directories) and leafs (=files).

	:ivar kindName: Name of the kind of data entities that are managed by the application. \
	This information is used to bind a specific :class:`server.skeleton.Skeleton`-class to the \
	application. For more information, refer to the function :func:`_resolveSkel`.\
	\
	In difference to the other ViUR BasicApplication, the kindName in Trees evolve into the kindNames\
	*kindName + "node"* and *kindName + "leaf"*, because information can be stored in different kinds.
	:vartype kindName: str

	:ivar adminInfo: todo short info on how to use adminInfo.
	:vartype adminInfo: dict | callable
	"""

	accessRights = ["add", "edit", "view", "delete"]  # Possible access rights for this app
	hasDistinctLeafs = False  # Set to True if we have a distinct Skeleton for leafs, else we'll work as a hierarchy

	def adminInfo(self):
		return {
			"name": self.__class__.__name__,  # Module name as shown in the admin tools
			"handler": "tree",  # Which handler to invoke
			"icon": "icons/modules/tree.svg"  # Icon for this module
		}

	def __init__(self, moduleName, modulePath, *args, **kwargs):
		super(Tree, self).__init__(moduleName, modulePath, *args, **kwargs)

	def _resolveSkelCls(self, skelType: TreeType, *args, **kwargs):
		"""
		Retrieve the generally associated :class:`server.skeleton.Skeleton` that is used by
		the application.

		This is either be defined by the member variable *kindName* or by a Skeleton named like the
		application class in lower-case order.

		If this behavior is not wanted, it can be definitely overridden by defining module-specific
		:func:`viewSkel`,:func:`addSkel`, or :func:`editSkel` functions, or by overriding this
		function in general.

		:return: Returns a Skeleton instance that matches the application.
		:rtype: server.skeleton.Skeleton
		"""
		baseName = self.kindName if self.kindName else str(type(self).__name__).lower()
		if skelType == TreeType.Node:  # FIXME: Do we map also to _node if we are a hierarchy?
			baseName += "_node"
		return skeletonByKind(baseBone)

	def viewSkel(self, skelType: TreeType, *args, **kwargs):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for viewing an existing entry from the list.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`addSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for viewing an entry.
		:rtype: server.skeleton.Skeleton
		"""
		if skelType.Leaf and not self.hasDistinctLeafs:
			# We don't have distinct leafs, so don't try to resolve a skeleton for it
			return None
		return self._resolveSkelCls(skelType, *args, **kwargs)()

	def addSkel(self, skelType: TreeType, *args, **kwargs):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for adding an entry to the list.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for adding an entry.
		:rtype: server.skeleton.Skeleton
		"""
		if skelType.Leaf and not self.hasDistinctLeafs:
			# We don't have distinct leafs, so don't try to resolve a skeleton for it
			return None
		return self._resolveSkelCls(skelType, *args, **kwargs)()

	def editSkel(self, skelType: TreeType, *args, **kwargs):
		"""
		Retrieve a new instance of a :class:`server.skeleton.Skeleton` that is used by the application
		for editing an existing entry from the list.

		The default is a Skeleton instance returned by :func:`_resolveSkel`.

		.. seealso:: :func:`viewSkel`, :func:`editSkel`, :func:`_resolveSkel`

		:return: Returns a Skeleton instance for editing an entry.
		:rtype: server.skeleton.Skeleton
		"""
		if skelType.Leaf and not self.hasDistinctLeafs:
			# We don't have distinct leafs, so don't try to resolve a skeleton for it
			return None
		return self._resolveSkelCls(skelType, *args, **kwargs)()


	## External exposed functions

	@exposed
	def listRootNodes(self, name=None, *args, **kwargs):
		"""
		Renders a list of all available repositories for the current user using the
		modules default renderer.

		:returns: The rendered representation of the available root-nodes.
		:rtype: str
		"""
		return self.render.listRootNodes(self.getAvailableRootNodes(name))

	@exposed
	def list(self, skelType, *args, **kwargs):
		"""
		Prepares and renders a list of entries.

		All supplied parameters are interpreted as filters for the elements displayed.

		Unlike other ViUR BasicApplications, the access control in this function is performed
		by calling the function :func:`listFilter`, which updates the query-filter to match only
		elements which the user is allowed to see.

		.. seealso:: :func:`listFilter`, :func:`server.db.mergeExternalFilter`

		:returns: The rendered list objects for the matching entries.

		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		"""
		if skelType == "node":
			skel = self.viewSkel(TreeType.Node)
		elif skelType == "leaf" and self.hasDistinctLeafs:
			skel = self.viewSkel(TreeType.Leaf)
		else:
			raise errors.NotAcceptable()
		query = self.listFilter(skel.all().mergeExternalFilter(kwargs))  # Access control
		if query is None:
			raise errors.Unauthorized()
		res = query.fetch()
		return self.render.list(res)

	@exposed
	def view(self, skelType, key, *args, **kwargs):
		"""
		Prepares and renders a single entry for viewing.

		The entry is fetched by its *key* and its *skelType*.
		The function performs several access control checks on the requested entity before it is rendered.

		.. seealso:: :func:`canView`, :func:`onItemViewed`

		:returns: The rendered representation of the requested entity.

		:param skelType: May either be "node" or "leaf".
		:type skelType: str
		:param node: URL-safe key of the parent.
		:type node: str

		:raises: :exc:`server.errors.NotAcceptable`, when an incorrect *skelType* is provided.
		:raises: :exc:`server.errors.NotFound`, when no entry with the given *key* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		"""
		if skelType == "node":
			skel = self.viewSkel(TreeType.Node)
		elif skelType == "leaf" and self.hasDistinctLeafs:
			skel = self.viewSkel(TreeType.Leaf)
		else:
			raise errors.NotAcceptable()
		if not key:
			raise errors.NotAcceptable()
		if key == u"structure":
			# We dump just the structure of that skeleton, including it's default values
			if not self.canView(skelType, None):
				raise errors.Unauthorized()
		else:
			# We return a single entry for viewing
			if not skel.fromDB(key):
				raise errors.NotFound()
			if not self.canView(skelType, skel):
				raise errors.Unauthorized()
			self.onItemViewed(skel)
		return self.render.view(skel)

	@exposed
	@forceSSL
	def add(self, skelType, node, *args, **kwargs):
		"""
		Add a new entry with the given parent *node*, and render the entry, eventually with error notes
		on incorrect data. Data is taken by any other arguments in *kwargs*.

		The function performs several access control checks on the requested entity before it is added.

		.. seealso:: :func:`onItemAdded`, :func:`canAdd`

		:param skelType: Defines the type of the new entry and may either be "node" or "leaf".
		:type skelType: str
		:param node: URL-safe key of the parent.
		:type node: str

		:returns: The rendered, added object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.NotAcceptable`, when no valid *skelType* was provided.
		:raises: :exc:`server.errors.NotFound`, when no valid *node* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		if skelType == "node":
			skel = self.viewSkel(TreeType.Node)
		elif skelType == "leaf" and self.hasDistinctLeafs:
			skel = self.viewSkel(TreeType.Leaf)
		else:
			raise errors.NotAcceptable()

		# FIXME: IsValidParent?
		#parentNodeSkel = self.editNodeSkel()
		#if not parentNodeSkel.fromDB(node):
		#	raise errors.NotFound()

		if not self.canAdd(skelType, node):
			raise errors.Unauthorized()

		if (len(kwargs) == 0  # no data supplied
				or skey == ""  # no security key
				# or not request.current.get().isPostRequest fixme: POST-method check missing? # failure if not using POST-method
				or not skel.fromClient(kwargs)  # failure on reading into the bones
				or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before adding
		):
			return self.render.add(skel)

		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		skel["parentdir"] = str(node)
		skel["parentrepo"] = parentNodeSkel["parentrepo"] or str(node)

		skel.toDB()
		self.onItemAdded(skel)

		return self.render.addItemSuccess(skel)

	@exposed
	@forceSSL
	def edit(self, skelType, key, skey="", *args, **kwargs):
		"""
		Modify an existing entry, and render the entry, eventually with error notes on incorrect data.
		Data is taken by any other arguments in *kwargs*.

		The function performs several access control checks on the requested entity before it is added.

		.. seealso:: :func:`onItemAdded`, :func:`canEdit`

		:param skelType: Defines the type of the entry that should be modified and may either be "node" or "leaf".
		:type skelType: str
		:param key: URL-safe key of the item to be edited.
		:type key: str

		:returns: The rendered, modified object of the entry, eventually with error hints.

		:raises: :exc:`server.errors.NotAcceptable`, when no valid *skelType* was provided.
		:raises: :exc:`server.errors.NotFound`, when no valid *node* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if skelType == "node":
			skel = self.viewSkel(TreeType.Node)
		elif skelType == "leaf" and self.hasDistinctLeafs:
			skel = self.viewSkel(TreeType.Leaf)
		else:
			raise errors.NotAcceptable()

		if not skel.fromDB(key):
			raise errors.NotFound()

		if not self.canEdit(skelType, skel):
			raise errors.Unauthorized()

		if (len(kwargs) == 0  # no data supplied
				or skey == ""  # no security key
				# or not request.current.get().isPostRequest fixme: POST-method check missing?  # failure if not using POST-method
				or not skel.fromClient(kwargs)  # failure on reading into the bones
				or ("bounce" in kwargs and kwargs["bounce"] == "1")  # review before adding
		):
			return self.render.edit(skel)

		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		skel.toDB()
		self.onItemEdited(skel)

		return self.render.editItemSuccess(skel)

	@exposed
	@forceSSL
	@forcePost
	def delete(self, skelType, key, *args, **kwargs):
		"""
		Deletes an entry or an directory (including its contents).

		The function runs several access control checks on the data before it is deleted.

		.. seealso:: :func:`canDelete`, :func:`onItemDeleted`

		:param skelType: Defines the type of the entry that should be deleted and may either be "node" or "leaf".
		:type skelType: str
		:param key: URL-safe key of the item to be deleted.
		:type key: str

		:returns: The rendered, deleted object of the entry.

		:raises: :exc:`server.errors.NotFound`, when no entry with the given *key* was found.
		:raises: :exc:`server.errors.Unauthorized`, if the current user does not have the required permissions.
		:raises: :exc:`server.errors.PreconditionFailed`, if the *skey* could not be verified.
		"""
		if skelType == "node":
			skel = self.viewSkel(TreeType.Node)
		elif skelType == "leaf" and self.hasDistinctLeafs:
			skel = self.viewSkel(TreeType.Leaf)
		else:
			raise errors.NotAcceptable()

		if "skey" in kwargs:
			skey = kwargs["skey"]
		else:
			skey = ""

		if not skel.fromDB(key):
			raise errors.NotFound()

		if not self.canDelete(skelType, skel):
			raise errors.Unauthorized()
		if not securitykey.validate(skey, useSessionKey=True):
			raise errors.PreconditionFailed()

		if skelType == "node":
			self.deleteRecursive(key)
		skel.delete()

		self.onItemDeleted(skel)
		return self.render.deleteSuccess(skel, skelType=skelType)

	@callDeferred
	def deleteRecursive(self, nodeKey):
		"""
		Recursively processes a delete request.

		This will delete all entries which are children of *nodeKey*, except *key* nodeKey.

		:param key: URL-safe key of the node which children should be deleted.
		:type key: str
		"""
		if self.hasDistinctLeafs:
			for f in db.Query(self.viewSkel(TreeType.Leaf).kindName).filter("parentdir", str(nodeKey)).iter(keysOnly=True):
				s = self.viewSkel(TreeType.Leaf)
				if not s.fromDB(f):
					continue
				s.delete()
		for d in db.Query(self.viewSkel(TreeType.Node).kindName).filter("parentdir", str(nodeKey)).iter(keysOnly=True):
			self.deleteRecursive(str(d))
			s = self.viewSkel(TreeType.Node)
			if not s.fromDB(d):
				continue
			s.delete()

	## Default access control functions

	def listFilter(self, filter):
		"""
		Access control function on item listing.

		This function is invoked by the :func:`list` renderer and the related Jinja2 fetching function,
		and is used to modify the provided filter parameter to match only items that the current user
		is allowed to see.

		:param filter: Query which should be altered.
		:type filter: :class:`server.db.Query`

		:returns: The altered filter, or None if access is not granted.
		:type filter: :class:`server.db.Query`
		"""
		user = utils.getCurrentUser()

		if user and ("%s-view" % self.moduleName in user["access"] or "root" in user["access"]):
			return filter

		return None


	def canView(self, skelType: TreeType, skel: Skeleton) -> bool:
		"""
		Checks if the current user can view the given entry.
		Should be identical to what's allowed by listFilter.
		By default, `meth:listFilter` is used to determine what's allowed and whats not; but this
		method can be overridden for performance improvements (to eliminate that additional database access).
		:param skel: The entry we check for
		:return: True if the current session is authorized to view that entry, False otherwise
		"""
		queryObj = self.viewSkel().all().mergeExternalFilter({"key": skel["key"]})
		queryObj = self.listFilter(queryObj)  # Access control
		if queryObj is None:
			return False
		if not queryObj.get():
			return False
		return True


	def canAdd(self, skelType: TreeType):
		"""
		Access control function for adding permission.

		Checks if the current user has the permission to add a new entry.

		The default behavior is:
		- If no user is logged in, adding is generally refused.
		- If the user has "root" access, adding is generally allowed.
		- If the user has the modules "add" permission (module-add) enabled, adding is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`add`

		:returns: True, if adding entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		# root user is always allowed.
		if user["access"] and "root" in user["access"]:
			return True

		# user with add-permission is allowed.
		if user and user["access"] and "%s-add" % self.moduleName in user["access"]:
			return True

		return False


	def canEdit(self, skelType: TreeType, skel):
		"""
		Access control function for modification permission.

		Checks if the current user has the permission to edit an entry.

		The default behavior is:
		- If no user is logged in, editing is generally refused.
		- If the user has "root" access, editing is generally allowed.
		- If the user has the modules "edit" permission (module-edit) enabled, editing is allowed.

		It should be overridden for a module-specific behavior.

		.. seealso:: :func:`edit`

		:param skel: The Skeleton that should be edited.
		:type skel: :class:`server.skeleton.Skeleton`

		:returns: True, if editing entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()
		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user and user["access"] and "%s-edit" % self.moduleName in user["access"]:
			return True

		return False


	def canDelete(self, skelType: TreeType, skel):
		"""
		Access control function for delete permission.

		Checks if the current user has the permission to delete an entry.

		The default behavior is:
		- If no user is logged in, deleting is generally refused.
		- If the user has "root" access, deleting is generally allowed.
		- If the user has the modules "deleting" permission (module-delete) enabled, \
		 deleting is allowed.

		It should be overridden for a module-specific behavior.

		:param skel: The Skeleton that should be deleted.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`delete`

		:returns: True, if deleting entries is allowed, False otherwise.
		:rtype: bool
		"""
		user = utils.getCurrentUser()

		if not user:
			return False

		if user["access"] and "root" in user["access"]:
			return True

		if user and user["access"] and "%s-delete" % self.moduleName in user["access"]:
			return True

		return False

	## Overridable eventhooks

	def onItemAdded(self, skel):
		"""
		Hook function that is called after adding an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		:param skel: The Skeleton that has been added.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`add`
		"""
		logging.info("Entry added: %s" % skel["key"])
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["key"]))

	def onItemEdited(self, skel):
		"""
		Hook function that is called after modifying an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		:param skel: The Skeleton that has been modified.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`edit`
		"""
		logging.info("Entry changed: %s" % skel["key"])
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["key"]))

	def onItemViewed(self, skel):
		"""
		Hook function that is called when viewing an entry.

		It should be overridden for a module-specific behavior.
		The default is doing nothing.

		:param skel: The Skeleton that is viewed.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`view`
		"""
		pass

	def onItemDeleted(self, skel):
		"""
		Hook function that is called after deleting an entry.

		It should be overridden for a module-specific behavior.
		The default is writing a log entry.

		..warning: Saving the skeleton again will undo the deletion
		(if the skeleton was a leaf or a node with no children).

		:param skel: The Skeleton that has been deleted.
		:type skel: :class:`server.skeleton.Skeleton`

		.. seealso:: :func:`delete`
		"""
		logging.info("Entry deleted: %s (%s)" % (skel["key"], type(skel)))
		user = utils.getCurrentUser()
		if user:
			logging.info("User: %s (%s)" % (user["name"], user["key"]))