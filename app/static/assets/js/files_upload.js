function UploadReport(apiUrl) {
    $("#uploadForm").on("submit", function (e) {
      e.preventDefault(); // 防止表單的默認提交行為

      // 禁用提交按鈕並顯示加載指示符
      $("#uploadButton").prop("disabled", true);
      $("#loadingIndicator").show();

      var formData = new FormData(this);

      $.ajax({
        type: "POST",
        url: apiUrl,
        data: formData,
        contentType: false,
        processData: false,
        success: function (response) {
          // 重新啟用按鈕並隱藏加載指示符
          $("#uploadButton").prop("disabled", false);
          $("#loadingIndicator").hide();

          // 清除文件上傳控件的內容
          $("#files").val("");

          // 顯示成功信息
          displayUploadResult(response.upload_success, response.file_name_list);
        },
        error: function (xhr) {
          // 重新啟用按鈕並隱藏加載指示符
          $("#uploadButton").prop("disabled", false);
          $("#loadingIndicator").hide();

          // 顯示錯誤信息
          var response = xhr.responseJSON;
          displayUploadResult(response.upload_success, response.file_name_list);
        },
      });
    });
  }

  function displayUploadResult(uploadSuccess, fileNameList) {
    $("#uploadResultBlock").show();
    
    var resultContainer = $("#uploadResultList");
    resultContainer.empty(); // 清空之前的結果

    var resultHtml = '';
    if (uploadSuccess) {
      resultHtml +=
        "<h3 class='card-title'>上傳結果：成功</h3><p>以下檔案已成功上傳到雲端資料庫；可繼續上傳</p>";
    } else {
      resultHtml +=
        "<h3 class='card-title'>上傳結果：失敗</h3><p>以下檔案檔名格式有誤，所有檔案皆未上傳，請修改以下錯誤檔名後，連同其餘檔案重新上傳</p>";
    }
    resultHtml += '<ul class="list-group">';
    fileNameList.forEach(function (fileName) {
      resultHtml += '<li class="list-group-item">' + fileName + "</li>";
    });
    resultHtml += "</ul></div>";

    resultContainer.html(resultHtml);
  }