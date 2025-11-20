document.getElementById("search-btn").addEventListener("click", () => {
  const pin = document.getElementById("pincode").value;
  const hosp = document.getElementById("hospital").value;

  if (!pin && !hosp) {
    alert("Please enter city/pincode or hospital name!");
    return;
  }
  alert(`Searching hospitals in "${pin}" with keyword "${hosp}"`);
});
