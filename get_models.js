fetch('https://openrouter.ai/api/v1/models')
  .then(res => res.json())
  .then(json => {
    json.data.forEach(m => {
      if(m.id.toLowerCase().includes('free')) {
        console.log(m.id);
      }
    });
  });
