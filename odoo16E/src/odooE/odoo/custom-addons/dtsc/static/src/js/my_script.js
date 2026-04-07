// 在my_script.js文件中添加以下代码
window.odoo.define('my_module.my_script', function (require) {
    'use strict';

    var rpc = require('web.rpc');
    var $ = require('jquery');

    $(document).ready(function() {
        $('#customer-search').on('input', function() {
            var searchValue = $(this).val();

            if (searchValue.length > 2) {
                rpc.query({
                    model: "res.partner",
                    method: "search_read",
                    args: [[["name", "ilike", searchValue]], ["name"]],
                    kwargs: {limit: 5},
                }).then(function(results){
                    var htmlString = '';

                    results.forEach(function(result) {
                        htmlString += '<p>' + result.name + '</p>';
                    });

                    $('#customer-search-results').html(htmlString);
                });
            } else {
                $('#customer-search-results').empty();
            }
        });
    });
});
