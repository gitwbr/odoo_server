odoo.define('dtsc.makein', function (require) {
    "use strict";
	console.log("start_makein")
	
	var rpc = require('web.rpc')
	window.deleteImage = function(model,recordId,imageUrl){
		// alert(recordId)
		rpc.query({
			model:model,
			method:'delete_image',
			args:[recordId,imageUrl],
		}).then(function(){
			location.reload();
		})
	}
    // var FormController = require('web.FormController');
	// FormController.include({
		// _render:function(){
			
			// console.log("update method is called")
			// this._super.apply(this,arguments);
			
			// var imageUrlsField = this.renderer.state.data.image_urls;
			// var iamgeUrls = JSON.parse(imageUrlsField);
			
			// var $imageGallery = $('#image_gallery');
			// $imageGallery.empty();
			
			// imageUrls.forEach(function (url){
				// console.log(url)
				// var $img = $('<img/>' , {
					// src:"http://43.156.27.132/uploads_makein/"+url,
					// width:'150px',
					// height:'auto'
					
				// });
				// $imageGallery.append($img)
			// })
			
		// }
		
	// })

	console.log("end_makein");
});