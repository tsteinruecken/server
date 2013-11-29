# -*- coding: utf-8 -*-
from server.skeleton import Skeleton
from server.applications.hierarchy import Hierarchy, HierarchySkel
from server.bones import *
from server import db
from server import session, errors
from server.plugins.text.youtube import YouTube
import logging

class pageSkel( HierarchySkel ):
	kindName="page"
	searchindex = "page"
	name = stringBone( descr="Name", indexed=True, searchable=True, required=True )
	descr = textBone( descr="Content", required=True, searchable=True, extensions=[YouTube] )
	hrk = baseBone( descr="Human readable key", visible=False, required=False, indexed=True, readOnly=True )
	
	def postProcessSerializedData( self, id,  dbfields ): #Build our human readable key
		obj = db.Get( db.Key( id ) )
		nr = db.Key( id ).id_or_name()
		try:
			name = unicode( self.name.value )
		except:
			name = ""
		hrk = "!%s-%s" % ( str( "".join( [ x for x in name.lower() if x in "0123456789 abcdefghijklmnopqrstuvwxyz"] ) ).replace(" ", "_"), nr )
		obj["hrk"] = hrk
		db.Put( obj )

class Page( Hierarchy ): 
	adminInfo = {	"name": "Sites", #Name of this modul, as shown in ViUR Admin (will be translated at runtime)
				"handler": "hierarchy",  #Which handler to invoke
				"icon": "icons/modules/hierarchy.svg", #Icon for this modul
				"formatstring": "$(name)", 
				"filters" : { 	
							None: { "filter":{ },
									"icon":"icons/modules/hierarchy.svg",
									"columns":["name", "language", "isactive"]
							},
					},
				"previewURL": "/page/view/{{id}}"
				}

	viewTemplate = "page_view"

	def view( self, id=None, *args, **kwargs ):
		if unicode(id).startswith("!"): #This is a human readable key
			repo = str(self.getAvailableRootNodes()[0]["key"])
			query = db.Query(  self.viewSkel().kindName )
			query.filter( "parentrepo =", repo )
			query.filter( "hrk =", id )
			entry = query.get()
			if entry:
				return( super( Page, self ).view( str( entry.key() ) ) )
		return( super( Page, self ).view( id, *args, **kwargs  )) 
	view.exposed = True

	def pathToKey( self, key=None ): #FIXME: Obsolete
		if unicode(key).startswith("!"): #This is a human readable key
			repo = str(self.getAvailableRootNodes()[0]["key"])
			query = db.Query(  self.viewSkel().kindName )
			query.filter( "parentrepo =", repo )
			query.filter( "hrk =", key )
			entry = query.get()
			if entry:
				return( super( Page, self ).pathToKey( str( entry.key() ) ) )
		return( super( Page, self ).pathToKey( key ))
	pathToKey.internalExposed=True

	def getAvailableRootNodes( self, *args, **kwargs ):
		repo = self.ensureOwnModulRootNode()
		return( [{"name":u"Seiten", "key": str( repo.key() ) }] )

	def canList( self, parent ):
		return( True )
		
	def canView( self, id ):
		return( True )
	
Page.jinja2 = True
Page.json = True
